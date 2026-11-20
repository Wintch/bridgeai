---
title: Protection (MCBs, RCDs, main switch, surge protection, fuses, selectivity)
scope: selection, coordination and installation of protective devices in low-voltage installations of buildings in Argentina (houses, apartments, offices, shops and common services of buildings); single-phase 220 V and three-phase 3x380/220 V supply, TT system
when_to_use: choosing or reviewing an MCB (curve, rating, breaking capacity); coordinating cable and protection; choosing an RCD (sensitivity, type AC/A/F/B, how many circuits); setting up the main switch or incoming switch; deciding whether an SPD or a voltage protector is needed; reviewing selectivity between panels; an RCD or an MCB that trips
related: [README.md, regulations-and-permits.md, grades-and-circuits.md, conductors-and-conduits.md, earthing.md, panels.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md]
as_of: 2026-11-15
sources: [AEA 90364-7-771 Viviendas, oficinas y locales unitarios (Ed. 2006 + corrigenda up to Apr 2017; still the edition sold in the AEA store as of 2026-11), AEA 90364-7-770 Viviendas unifamiliares hasta 63 A (Ed. 2017 in force, text consulted; Ed. 2026 digital on sale and print on pre-order with delivery from 2026-11-16), AEA 90364-7-772 Espacios comunes y servicios generales (Ed. 2019), AEA 90364-7-722 Vehículos eléctricos (Ed. 2024), AEA 90364-4 and 90364-5 sections 443 and 534 (Ed. 2006), AEA 92305 / IRAM 2184 lightning protection (2015-2016), IEC 60898-1, IEC 61008-1 (Ed. 4.0, 2024), IEC 61009-1, IEC 62423, IEC 61643-11, IEC 63052 (2019), IEC 60269, IEC 60364-4-43 (434.5.2), IEC 60364-5-53 (sections 534 and 535, revision 2015/2019), IEC 60947-4-1 (starter coordination), Res. SIyC 236/2024 with Anexo II as per Res. SIyC 26/2025 + Disp. DNRT 2/2025 (materials for electrical installations), Res. ENRE 303/2025 (Edesur) and 304/2025 (Edenor) Subanexo 4 period 2025-2030, Res. ENRE 269/2012 (DCI), APSE in Ingeniería Eléctrica Nov 2015]
---
# Protection

What protects whom, how each device is chosen and how they are coordinated with each other. Each rule has an ID (`ELEC-PRO-n`) so that
the agent, a report or a message can cite it ("does not comply with ELEC-PRO-4: 25 A MCB (*térmica*) on 2.5 mm² cable"). Numerical
values carry their source; where it could not be confirmed in a primary source, this is stated.

The calculations (design current, Ib/In/Iz coordination, I²t, short-circuit current at a point, maximum length) are done by the agent
with the offline calculator `gateway electricidad ...` (current, voltage drop, cross-section, demand/grade,
coordination, earth), not from memory. The worked examples below are there to understand the calculation and to check the result.

**Safety first.** Changing, adding or readjusting a protective device is work on the panel: it is done **dead**, with the
circuit or the panel isolated upstream, locked out and tagged, and verified dead with a two-pole voltage tester
(IEC 61243-3) or a CAT III multimeter, testing it **before and after** on a live source and measuring L-N, L-PE and N-PE
(see [site-safety.md](site-safety.md), ELEC-SEG-3 and ELEC-SEG-5). The non-contact voltage tester (*lapicito*) is not good enough
to confirm absence of voltage. Switching off the MCB (*térmica*) of the circuit itself is not enough: the input terminals stay live.
The terminals of the utility service box (*caja de toma*), the NH fuses of the utility (*distribuidora*) and the line before the meter are not touched by the installer.

**The main switch next to the meter is the most dangerous case.** Its input terminals come from the meter output and
stay **live even when it is open**; upstream there is only utility equipment (meter, busbars, NH fuses), which the
installer cannot isolate. To change it, the utility does the disconnection: ask for the supply to be cut or for the meter/fuse to be removed,
or make the change during the initial connection. The main switch is **never** changed live, and the meter is never bypassed to do it
(see [site-safety.md](site-safety.md) and [regulations-and-permits.md](regulations-and-permits.md)).

**Clamp measurements.** Some of the checks below (current with a clamp meter, leakage with a leakage clamp meter, neutral
current) are made with the installation in service: they are **live measurements**. Only a trained person makes them, with
an IEC 61010 CAT III 600 V or CAT IV 300 V instrument as a minimum (CAT IV near the meter, ELEC-SEG-13), insulating gloves and face
protection, clamping around insulated conductors, without removing the inner cover (dead front, *contratapa*) (or with the live parts covered), and never an untrained
user. Safer alternative: measure on the appliance cable with a line splitter (clamp adapter).

## Standards and editions used in this guide (as of 2026-11-15)
| Document | Edition | What it is for here |
|---|---|---|
| AEA 90364-7-771 Viviendas, oficinas y locales (unitarios) (dwellings, offices and single shops) | 2006 + corrigenda (the latest listed, Apr 2017) | Base rule for apartments, offices and shops; Iz tables (771.16), protection (771.18, 771.19), panels (771.20), short-circuit annex H |
| AEA 90364-7-770 Viviendas unifamiliares hasta 63 A e Icc ≤ 10 kA (single-family houses up to 63 A and Icc ≤ 10 kA) | Ed. 2017 + Corrigendum 1 (the one that was read); Ed. 2026: the digital version is already on sale in the AEA store and the print version on pre-order (delivery announced from 2026-11-16), with no published date of entry into force | Same logic as the 771, summarized; the clauses cited below are from Ed. 2017: check numbering and changes as soon as the 2026 edition is published |
| AEA 90364-7-772 Espacios comunes y servicios generales (common areas and common services) | 2019 | Common services of a building (landing, pumps, elevator) |
| AEA 90364-7-722 Suministro a vehículos eléctricos (supply to electric vehicles) | 2024 | RCD (*disyuntor* / *diferencial*) type for chargers |
| AEA 90364-4 (section 443) and 90364-5 (section 534) | 2006 | Transient overvoltages and SPDs (*DPS*) |
| IEC 60898-1 | current | Miniature circuit breakers (PIA, *térmicas*) |
| IEC 61008-1 / IEC 61009-1 / IEC 62423 | 61008-1 Ed. 4.0 (Nov 2024) | RCDs without overcurrent protection / combined (RCBO) / types F and B |
| IEC 61643-11 | current | SPDs for low voltage |
| IEC 60364-5-53 (sections 534 SPD and 535 coordination) | 2015 revision of 534; ed. 2019 | Newer values than AEA 90364-5 Ed. 2006 (which follows IEC 2001) |
| IEC 60947-4-1 | current | Motor protection circuit breakers (*guardamotores*), contactors and their coordination (type 1 / type 2) |
| Res. ENRE 303/2025 (Edesur) and 304/2025 (Edenor), Subanexo 4 | period 2025-2030 | Supply voltage tolerance in the Edenor/Edesur area |

Sources: AEA store and addenda (aea.org.ar/reglamentaciones, aea.org.ar/addenda-corrigenda), foreword of the 771 Ed. 2006,
IEC/AFNOR catalogs for IEC 61008-1:2024. A 4-story building with apartments falls under the 771 (each unit) and the 772
(common services); the 770 is only for the simple single-family house.

**Verification note (revision 2026-11-15).** Several AEA clauses (especially 770.x of Ed. 2017) and the IEC values of
sections 534/535 could not be reconfirmed online in this revision: web search was exhausted and the official
portals returned errors. The calculations were redone by hand and the IEC values were reviewed against what is known of the standards.
Where the citation is from memory, the rule says so.

## Quick reference
| Situation | Rule |
|---|---|
| Which MCB to use (two-pole, standard, lockout) | ELEC-PRO-1 |
| B, C or D curve | ELEC-PRO-2 |
| How many kA it has to break | ELEC-PRO-3 |
| Which rating for a given cable | ELEC-PRO-4, table "Cross-section → maximum PIA" |
| Verify short circuit (I²t, maximum length) | ELEC-PRO-5 |
| "The MCB trips, I'll put in a bigger one" | ELEC-PRO-6 |
| 30 mA RCD: where | ELEC-PRO-7, ELEC-PRO-8 |
| Type AC, A, F or B | ELEC-PRO-9 |
| RCD rating and its protection | ELEC-PRO-10 |
| How many circuits per RCD / leakage trips | ELEC-PRO-11 |
| Upstream RCD (300 mA, selective S) | ELEC-PRO-12 |
| Test button | ELEC-PRO-13 |
| Main switch and incoming switch; neutral | ELEC-PRO-14, ELEC-PRO-15 |
| SPD: whether it is needed; which one; how it is installed | ELEC-PRO-16, ELEC-PRO-17, ELEC-PRO-18 |
| Broken neutral, high or low voltages | ELEC-PRO-19 |
| NH / cartridge fuses | ELEC-PRO-20 |
| Selectivity between panels | ELEC-PRO-21, ELEC-PRO-12 |
| Certified materials, mixing brands | ELEC-PRO-22 |
| Arc fault detection device (AFDD) | ELEC-PRO-23 |
| Pumps, elevator, common-services motors | ELEC-PRO-24 |
| Neutral through the ID, PE never; mixed neutrals, N-PE jumper | ELEC-PRO-25 |
| Old installation: plug fuses, knife switch, single-pole devices | ELEC-PRO-26 |
| Generator set and changeover switch | ELEC-PRO-27 |
| Busbar combs (*peines*), terminal torque, MCBs that heat up in the panel | ELEC-PRO-28 |
| Coordination with the utility's NH fuse | ELEC-PRO-29 |
| DCI requirement (ENRE area): ID ≤ 30 mA | ELEC-PRO-7; [regulations-and-permits.md](regulations-and-permits.md) |

### Miniature circuit breakers (IEC 60898-1)
| Item | Values | Source |
|---|---|---|
| Preferred rated currents | 6, 8, 10, 13, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125 A (on the Argentine market the usual range is 10 to 63 A; 8 and 13 A are hard to find) | IEC 60898-1, 5.3.2 (preferred values); manufacturers' catalogs |
| Magnetic (instantaneous) trip, B curve | between 3 and 5 In | IEC 60898-1 |
| C curve | between 5 and 10 In | IEC 60898-1 |
| D curve | between 10 and 20 In | IEC 60898-1 |
| Conventional non-tripping / thermal tripping | 1.13 In does not trip in 1 h; 1.45 In trips in less than 1 h (In ≤ 63 A) | IEC 60898-1; APSE, Ingeniería Eléctrica Nov 2015 |
| Standard breaking capacity (Icn) | 1 500 (hardly sold), 3 000, 4 500, 6 000, 10 000 A, and higher values up to 25 000 A; marked on the front inside a rectangle, in A. Above that: IEC 60947-2 circuit breakers | IEC 60898-1, 5.3.4; AEA 770 Ed. 2017, 770.15.2.2.2; APSE Nov 2015 |
| Energy limiting class | 1 (no marking, not limiting), 2 or 3 (number inside a square; 3 is the most limiting) | AEA 770 Ed. 2017 annex 770-B.2.3; APSE Nov 2015 |

### Cross-section → maximum PIA (IRAM NM 247-3 cables in conduit, copper, PVC)
Reference Iz: method B1, reference ambient temperature of 40 °C from the AEA table (valid for the whole country; at another
temperature the correction factor is applied), a single circuit in the conduit, see table 771.16.I of the 771
(equivalent to table 770.12.I of the 770 Ed. 2017). Grouping factor: 0.8 for 2 circuits and 0.7 for 3 circuits in
the same conduit (table 770.12.II). The PIA is the next standard rating **lower than or equal to** the corrected Iz.

| Cross-section [mm²] | Iz single-phase, 1 circuit [A] | Max. PIA 1 circuit | Max. PIA by Iz, 2 circuits in the conduit (×0.8) ¹ | Max. PIA by Iz, 3 circuits (×0.7) ¹ | Iz three-phase, 1 circuit [A] | Max. PIA three-phase |
|---|---|---|---|---|---|---|
| 1.5 | 15 | 13 A (10 A if you can't find 13) | 10 A | 10 A | 14 | 13 A |
| 2.5 | 21 | 20 A | 16 A | 10 A (13 A only if ΣIn ≤ 36 A, e.g. 13 + 13 + 10 A) | 18 | 16 A |
| 4 | 28 | 25 A | 20 A | 16 A | 25 | 25 A |
| 6 | 36 | 32 A | 25 A | 25 A | 32 | 32 A |
| 10 | 50 | 50 A (40 A recommended) | 40 A | 32 A | 44 | 40 A |
| 16 | 66 | 63 A | 50 A | 40 A | 59 | 50 A |
| 25 | 88 | 80 A | 63 A | 50 A | 77 | 63 A |
| 35 | 109 | 100 A | 80 A | 63 A | 96 | 80 A |

¹ The 2- and 3-circuit columns give only the limit by Iz. In buildings (770/771) only up to
3 **general-purpose** circuits, of the same phase and panel, with **ΣIn ≤ 36 A** and **≤ 15 outlet points (*bocas*)** in total, may share a conduit
([conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-10, [current-ratings-and-devices.md](current-ratings-and-devices.md)
ELEC-AMP-3): 3 × 13 A = 39 A is not allowed, and neither is 2 × 20 A = 40 A (with 4 mm², 20 + 16 A at most). Special-use
or specific-use circuits go in their own conduit, so the rows from 6 mm² upward with 2 or 3 circuits
only apply to other permitted groupings (for example, up to three sub-mains of sheathed cable from the same meter
in one conduit, ELEC-CON-10).

Besides the cable, the circuit type sets the limit: IUG maximum 16 A, TUG maximum 20 A, TUE maximum 32 A (table of circuit types of
771.7 / 770.6.I); and the minimum cross-sections (1.5 mm² IUG, 2.5 mm² TUG/TUE) from [grades-and-circuits.md](grades-and-circuits.md) and
[conductors-and-conduits.md](conductors-and-conduits.md). With a temperature other than 40 °C, cables on a cable tray,
buried or sheathed (IRAM 2178), use the corresponding table and the calculator.

### RCDs (*interruptores diferenciales*)
| Type (marking) | Detects | Use it for | Source |
|---|---|---|---|
| AC | Sinusoidal AC leakage | Resistive loads and ordinary motors without electronics. It is the most common on the Argentine market | IEC 61008-1:2024 4.3; AEA 770 Ed. 2017 note in 770.14.2.3 |
| A | AC + pulsating DC (+ up to 6 mA of smooth DC) | Circuits with single-phase electronics: induction cooktop, power supplies, chargers; **recommended** for LED lighting and general-purpose socket outlets. Minimum required for each EV charging point | IEC 61008-1:2024; AEA 90364-7-722:2024, 722.531.2.101 (see numbering note in ELEC-PRO-9) and table 722.I |
| F | A + mixed-frequency leakage up to 1 kHz (+ up to 10 mA of smooth DC) | Equipment with a single-phase variable-speed drive: inverter AC, inverter washing machine, pumps with a drive (type A as a minimum if the equipment manufacturer allows it) | IEC 62423; AEA 722:2024 table 722.I |
| B | F + smooth DC (trips on smooth DC at 2 IΔn at most) and AC up to 1 kHz | EV charger without DC detection, three-phase drives, PV inverters that require it | IEC 62423 (smooth DC threshold between 0.5 and 2 IΔn, from memory: confirm it in the manufacturer's data sheet); AEA 722:2024 |
| S (selective, time-delayed) | Same as its type, with a delay | Upstream of other IDs, for selectivity (ELEC-PRO-12) | IEC 61008-1:2024 4.4.2; AEA 770 Ed. 2017 770.14.3.2 b) |

| Tripping times (general-type ID, AC and A, limit values) | Source |
|---|---|
| Must not trip at 0.5 IΔn; must trip between 0.5 and 1 IΔn | IEC 61008-1 (table of limit times); AEA 722:2024 table 722.I |
| At IΔn: ≤ 300 ms; at 2 IΔn: ≤ 150 ms; at 5 IΔn: ≤ 40 ms | IEC 61008-1 (see table 11 of Ed. 2024); medium confidence, values from memory that match [testing-and-commissioning.md](testing-and-commissioning.md) |
| Type S at IΔn: between 130 and 500 ms; at 5 IΔn: between 50 and 150 ms | IEC 61008-1; **Not verified in a primary source:** values from memory, confirm them in the manufacturer's data sheet |

## Rules

### ELEC-PRO-1: Every circuit with an IEC 60898-1 MCB (*térmica*) that breaks all poles
- **Rule:** every sub-main and final circuit has its own circuit breaker (PIA) complying with IEC 60898-1, opening on overload and short circuit. In single-phase, **two-pole with protection on both poles**; in three-phase, four-pole (or three-pole + neutral as per ELEC-PRO-15). It opens all its poles at the same time. The **incoming** device of the panel must allow locking in the open position (seal, padlock or the manufacturer's lockout accessory); on final-circuit PIAs the lockout is an accessory, not a requirement for each one.
- **Why:** in Argentina phase and neutral can be swapped (in the network, at the meter or in a miswired socket outlet): a device that breaks only one pole can leave the phase connected with the MCB switched "off". The AEA prohibits single-pole devices, two-pole devices with "unprotected neutral", "neutral pass-through" or marked 1P+N, and also combined MCB-RCD devices with protection on only one pole, in single-phase installations.
- **How:** ask for "bipolar 2P" (two-pole 2P) or "2x16 A"; check that there is a protection symbol (thermal and magnetic) on both poles in the diagram printed on the front. In the single-line diagram (*unifilar*) state curve, rating and breaking capacity (e.g. "C 2x16 A 4,5 kA"). To work on a circuit, put the lockout accessory on its PIA or switch off and lock out the incoming device.
- **Verify:** with the PIA open, there is no voltage on either of the two output terminals with respect to earth (measurement made by a trained person, see [testing-and-commissioning.md](testing-and-commissioning.md)); the front shows "IEC 60898-1" and the breaking capacity in a rectangle.
- **Don't:** use a "1P+N" because it takes one module; protect a circuit with a switch-disconnector that has no trip; put the MCB only on the phase and run the neutral straight through.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.16.5.1 and 770.16.5.2; AEA 90364-7-771 Ed. 2006, 771.20.5 (the foreword of the 771 states that the 2006 edition "establece claramente la necesidad de corte bipolar, tripolar o tetrapolar según el tipo de circuito" (clearly establishes the need for two-pole, three-pole or four-pole breaking depending on the type of circuit)). **Not verified in a primary source:** the exact text on lockout in 770.16.5.x (in this revision it is interpreted as a requirement for the incoming device; lockouts for modular PIAs are catalog accessories).
### ELEC-PRO-2: Choose the curve by the load and by the minimum short-circuit current
- **Rule:** **C** curve for general use in houses and offices (socket outlets, lighting with LED drivers, small motors); **B** curve when the circuit is long or the available short-circuit current is low (far end of the line, generator); **D** curve only for loads with very high starting current (transformers, motors with heavy starting), almost never in houses.
- **Why:** the magnetic (instantaneous) trip has to happen with the *minimum* short-circuit current at the end of the circuit. With a D curve it takes up to 20 In for it to trip instantly: in a long circuit that may not be reached and the cable overheats before it breaks. With B, motor starting or the inrush of many LED drivers can make it trip with no fault.
- **How:** C by default; B if the maximum length check (ELEC-PRO-5) does not work out with C; D only with justification and checking the length. The AEA panel examples use B 2x16 and C 2x16 on house circuits.
- **Verify:** the circuit length is less than the maximum for that cross-section, rating and curve (table 771-H / 770-B.VII or the calculator).
- **Don't:** change C for D "because it trips on starting" without investigating the cause (see [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Source:** IEC 60898-1 (bands B 3-5 In, C 5-10 In, D 10-20 In); AEA 90364-7-770 Ed. 2017, 770.15.2.2.4 and table 770-B.VII (maximum length for instantaneous tripping by curve); AEA 771 annex H.

### ELEC-PRO-3: Breaking capacity greater than or equal to the prospective short-circuit current at that point
- **Rule:** every device that protects against short circuit must have a breaking capacity (PdCcc, the number in the rectangle) **≥ the maximum prospective Ik" at the point where it is installed**. The starting figure (Icc at the meter terminals or at the service box) is given by the utility (*distribuidora*); downstream it is calculated. It is written down in the technical report (*memoria técnica*).
- **Why:** a PIA that breaks fewer kA than the fault may fail to extinguish the arc, weld shut or explode. The AEA does not set a single kA value for everyone: it sets the rule, and the value comes from the network. The usual ones on the market are 3 000, 4 500, 6 000 and 10 000 A (IEC 60898-1 also standardizes 1 500 A and values up to 25 000 A; above that, IEC 60947-2 circuit breakers are used).
- **How:**
  1. Ask the utility for the maximum Icc at the supply point (the 770 makes this an obligation of the utility); if they don't give it, calculate it from the transformer and the network (annex H of the 771, AEA 90909-0) with the calculator.
  2. Calculate the Icc at each panel: the line impedance lowers it.
  3. Choose the next higher standard PdCcc. APSE example: 3 200 A prospective → 4 500 A PIA.
  4. Practical criterion: in the meter cabinet of a building (close to the network or to the building's own transformer) don't go below 6 kA without data; 10 kA if there is a transformer in the building or the utility reports more than 6 kA. In the apartment panel, after the sub-main (feeder), 4.5 kA is usually enough (see example), but it is verified.
  5. Practical alternative to check the figure: measure the phase-neutral loop impedance at the point with a loop impedance tester (IEC 61557-3); the instrument gives the prospective Icc. It is a **live measurement** (trained person, see "Clamp measurements" above and ELEC-MED-9). The measurement gives that day's Icc: the network may be reinforced (new transformer, thicker cable) and raise it. Use it to check the calculation and for the minimum Icc; for the breaking capacity, keep the highest of the measured, the calculated and the reported values.
- **Worked example (phase-neutral Icc on arrival at the apartment):** the utility reports maximum phase-neutral Icc at the meter cabinet = 6 000 A. For the maximum Icc the voltage factor c = 1.1 is used (IEC 60909-0 / AEA 90909-0), so the equivalent source impedance is Zs = 1.1 × 220 V / 6 000 A = 242 / 6 000 = 0.0403 Ω. Sub-main of 20 m, 2 x 10 mm² copper (the same as in the example building case; ρ = 0.0178 Ω·mm²/m at 20 °C, which gives the maximum Icc): R = 2 × 0.0178 × 20 / 10 = 0.0712 Ω.
  - Arithmetic sum (quick approximation): Icc ≈ 242 / (0.0403 + 0.0712) = 242 / 0.1115 ≈ **2 170 A**.
  - Vector sum, if the source impedance is almost all reactive (usual near a transformer): |Z| = √(0.0403² + 0.0712²) = √(0.00162 + 0.00507) = 0.0818 Ω → Icc ≈ 242 / 0.0818 ≈ **2 960 A**.
  - Conclusion: the arithmetic sum underestimates the Icc (it is not conservative for breaking capacity). With almost 3 kA, a 3 kA PIA is at the limit: the apartment panel gets **4.5 kA**. In the meter cabinet, ≥ 6 kA. The proper calculation is done by the calculator `gateway electricidad`.
- **Verify:** every PIA in the single-line diagram has PdCcc ≥ the Icc calculated at its panel; the report contains the utility's figure or the calculation.
- **Don't:** buy all PIAs at 3 kA "because it's a house" without data; rely on the upstream protection to use a PIA with lower breaking capacity (cascading or "back-up") without a manufacturer's table certifying that exact combination.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.15.2.2.2 (rule PdCcc ≥ Ik", utility figure, technical report); AEA 90364-7-771 Ed. 2006, annex 771-H.2 "Consideraciones acerca de las corrientes de cortocircuito" (considerations on short-circuit currents) (cited by APSE, Ingeniería Eléctrica Nov 2015, which gives the example 3 200 A → 4 500 A); IEC 60364-4-43 (434.5.1, back-up protection) cited by Ingeniería Eléctrica; IEC 60909-0, table 1 (cmax = 1.10 in LV); IEC 61557-3 (loop impedance testers). **Not verified in a primary source:** the Icc value that Edenor/Edesur report for T1 (their technical sheets could not be read); the 6/10 kA criterion is practice, not standard text.

### ELEC-PRO-4: Cable-protection coordination: Ib ≤ In ≤ Iz and I2 ≤ 1.45 Iz
- **Rule:** for each circuit: design current Ib ≤ rated current of the PIA In ≤ current-carrying capacity of the cable Iz **already corrected** (temperature, grouping, installation method). And the conventional tripping current I2 ≤ 1.45 Iz.
- **Why:** if In > Iz, the cable can stay overloaded for hours without the MCB (*térmica*) breaking: the insulation degrades and a fire starts. With IEC 60898-1 PIAs, I2 = 1.45 In, so the second condition is met by itself if In ≤ Iz is met. With gG fuses it is not (ELEC-PRO-20).
- **How:** (single-phase) Ib = P / (U × cos φ). Choose a standard In ≥ Ib and verify In ≤ Iz × factors.
- **Worked example:** TUE circuit for a 3 000 W air conditioner, cos φ = 0.9, 220 V: Ib = 3 000 / (220 × 0.9) = **15.2 A**. 2.5 mm² cable in a conduit shared with another circuit: Iz = 21 A × 0.8 = **16.8 A**. PIA C 2x16 A: 15.2 ≤ 16 ≤ 16.8 ✔. I2 = 1.45 × 16 = 23.2 A ≤ 1.45 × 16.8 = 24.4 A ✔. With a 20 A PIA it does not comply (20 > 16.8): either go down to 16 A or go up to 4 mm².
  - **Small margin:** it complies on paper, but with Ib at 95 % of In and the PIA calibrated at 30 °C inside a panel at 40 °C or more (its thermal threshold drops, ELEC-PRO-28), it will trip in summer and pushes toward the mistake in ELEC-PRO-6. Better: **4 mm² with C 2x20 A**: Iz = 28 × 0.8 = 22.4 A; 15.2 ≤ 20 ≤ 22.4 ✔.
  - **The input figure:** the 3 000 W is **electrical input power** (nameplate or manual, in W or A). Don't use frigories or "cooling W": a 3 000-frigorie unit draws on the order of 1 000-1 200 W electrical (see ELEC-ESP-10 in [special-installations.md](special-installations.md)).
- **Verify:** in the single-line diagram, next to each PIA: Ib, cross-section, method, factors, corrected Iz. The calculator `gateway electricidad` does the coordination.
- **Don't:** use the Iz table "in free air" or at 30 °C for cables in embedded conduit; forget the grouping factor when several circuits run in the same conduit; choose the cable by the PIA "that is always used".
- **Source:** AEA 90364-7-770 Ed. 2017, 770.15.2.1 and figure 770.15.A; AEA 90364-7-771 Ed. 2006, 771.19.2 and 771.19.3 (calculation steps), tables 771.16; APSE, "Verificaciones para realizar en conductores y protecciones" (checks to perform on conductors and protection), Ingeniería Eléctrica Nov 2015 (I2 = 1.45 In for IEC 60898).

### ELEC-PRO-5: Verify the short circuit: let-through energy (I²t ≤ k²S²) and minimum current
- **Rule:** besides overload, every cable has to withstand the energy of the maximum short circuit until the protection breaks (**k²·S² ≥ I²t**), and the *minimum* short-circuit current (at the end of the circuit) has to make the PIA trip instantaneously.
- **Why:** with high Icc and a thin cable, the conductor can exceed its limit temperature (160 °C for PVC) in milliseconds; with a long circuit, the Icc at the end can fall below the magnetic trip and the PIA takes seconds.
- **How:**
  - k = 115 for PVC-insulated copper (70 °C → 160 °C), table 771.19.II / 770.15.II.
  - If the break is **instantaneous** (t < 0.1 s: magnetic zone, or a current-limiting device), use the I²t guaranteed by the manufacturer for that PIA at the Icc of the point. As a guide: tables 771-H.2.4 / 770-B.VIII and B.IX give the maximum I²t by limiting class and breaking capacity. If the PIA does not declare I²t (class 1, hardly sold), buy one that declares it (class 3).
  - Only when the breaking time, **read on the curve** of the device for that current, is **between 0.1 s and 5 s**, does the adiabatic formula apply: t ≤ (k × S / I)², that is S ≥ I × √t / k.
  - Minimum current: maximum length from tables (771-H / 770-B.VII) or the simplified formula Lmax ≈ 0.8 × U0 × S / (2 × ρ × Ia), with Ia = upper magnetic trip of the curve (10 In for C) and ρ ≈ 0.0225 Ω·mm²/m (hot copper, conservative).
- **Example 1 (I²t, current-limiting PIA):** TUG 2.5 mm², PIA C16, 6 kA, class 3; Icc at the panel 3 000 A. k²S² = 115² × 2.5² = 13 225 × 6.25 = **82 656 A²s**. Indicative maximum I²t for C, ≤ 16 A, 6 000 A, class 3 = **42 000 A²s** (table 770-B.VIII). 42 000 ≤ 82 656 ✔. (This is the AEA's own example.)
- **Example 2 (non-limiting PIA, instantaneous break):** 4 mm² line, PIA C25 with no limiting class, Icc 3 200 A. 3 200 A is 128 In, far above the magnetic band of the C curve (10 In = 250 A): it breaks in one half-cycle or less (≈ 10 ms). Estimate: I²t ≈ 3 200² × 0.01 = 10 240 000 × 0.01 = **102 400 A²s** < k²S² = 13 225 × 16 = **211 600 A²s** ✔. It is an estimate: the correct figure is the manufacturer's guaranteed I²t. With a 4.5 kA class 3 PIA the margin is much larger (indicative I²t for C, 16-32 A, 4 500 A, class 3 = 39 000 A²s, table 770-B.IX).
- **Example 2b (time-delayed protection, a case that fails):** 2.5 mm² branch protected only by an incoming switch with a short-circuit delay of 0.3 s (read from its setting), Icc 1 500 A. I²t = 1 500² × 0.3 = **675 000 A²s** > k²S² = 82 656 A²s ✘. Minimum cross-section: S ≥ 1 500 × √0.3 / 115 = 1 500 × 0.548 / 115 = **7.1 mm²** → 10 mm² (k²S² = 13 225 × 100 = 1 322 500 A²s ✔), or better, a dedicated PIA on the branch.
- **Example 3 (maximum length):** 2.5 mm², C16 → Ia = 160 A. With hot copper ρ (0.0225): Lmax ≈ 0.8 × 220 × 2.5 / (2 × 0.0225 × 160) = 440 / 7.2 ≈ **61 m**. With cold copper ρ (0.0178): 440 / (2 × 0.0178 × 160) = 440 / 5.696 ≈ **77 m**. The value in table 770-B.VII / 771-H depends on its assumptions (**Not verified in a primary source** in this revision); adding the source impedance shortens the length, it does not lengthen it. If your circuit is longer than about 60 m, calculate with the calculator or switch to a B curve.
- **Verify:** calculation report with k²S², the manufacturer's I²t (or the guidance table) and actual length ≤ maximum length, per circuit.
- **Don't:** take the protection of a 1.5 mm² cable as good with any 6 kA PIA: a C10 6 kA class 3 can let through up to 42 000 A²s and the cable withstands 115² × 1.5² = 29 756 A²s; if the actual Icc at the point is high, it fails.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.15.2.2.3, 770.15.2.2.4, table 770.15.II, annex 770-B.2.2 and B.2.3 (tables VII, VIII and IX and example C16 6 kA); AEA 90364-7-771 Ed. 2006, table 771.19.II and annex 771-H.2.4 (cited by APSE, Ingeniería Eléctrica Nov 2015); IEC 60364-4-43, 434.5.2 (adiabatic formula for durations up to 5 s; below 0.1 s and with current-limiting devices, k²S² is compared with the manufacturer's I²t; AEA 771.19.2 / 770.15.2.2.3 follows the same logic). The simplified Lmax formula is manufacturers' practice, not AEA text.

### ELEC-PRO-6: If the MCB (*térmica*) trips, don't increase its rating
- **Rule:** the rating of the PIA is set by the cable (ELEC-PRO-4) and the circuit type, not by the user's annoyance. If it trips on overload, the load is split or a new circuit is added; if it trips instantly, there is a short circuit or an abnormal inrush that has to be found.
- **Why:** changing a 16 A for a 25 A on a 2.5 mm² cable leaves the cable without overload protection: it is the classic cause of burnt cables inside the wall.
- **How:** measure the actual current with a clamp meter (live measurement: trained person, CAT III, PPE, without removing the inner cover (*contratapa*); see "Clamp measurements" at the beginning); add up the loads of the circuit; check whether it trips after minutes (overload) or immediately (short circuit or inrush). See [troubleshooting-common-cases.md](troubleshooting-common-cases.md).
- **Verify:** the installed PIA matches the one in the single-line diagram and the table "Cross-section → maximum PIA".
- **Don't:** bypass it, "tie" the lever or fit a higher-rated PIA "temporarily".
- **Source:** direct consequence of AEA 771.19.2 / 770.15.2.1 (Ib ≤ In ≤ Iz).

### ELEC-PRO-7: 30 mA instantaneous RCD (*disyuntor* / *diferencial*) on all final circuits
- **Rule:** **all** final circuits (IUG, TUG, TUE and specific-use) must be protected by an RCD with IΔn ≤ 30 mA, without time delay. It is **additional** protection against direct contact: it does not replace insulation, enclosures or earthing.
- **Why:** 30 mA is the threshold that breaks before the current through the body becomes dangerous to the heart in most cases. But it does not protect against contact with phase and neutral at the same time (the current does not "leak" to earth) and it does not limit the fault current: that is why it is additional.
- **How:** 30 mA ID in the apartment sub-panel (TS, *tablero seccional*), by groups of circuits (ELEC-PRO-11), or a combined device (RCBO, IEC 61009-1) per circuit. IDs must comply with IEC 61008 (RCD only) or IEC 61009 (with built-in overcurrent protection). In the Edenor/Edesur area (ENRE, now ENReGE; Edelap is under OCEBA, see ELEC-NOR-13), the DCI (installation conformity declaration) (Res. ENRE 269/2012, item 3.8) requires an ID ≤ 30 mA in the main panel, protected against overload and short circuit; according to note 2 of the form, if there is a main panel and a sub-panel, the ID can go in the sub-panel and the MCB in the main panel (details in [regulations-and-permits.md](regulations-and-permits.md)). With a "NO" on that item there is no meter.
- **Verify:** test with an RCD tester at commissioning (does not trip at 0.5 IΔn; trips at IΔn within the time limit); test button (ELEC-PRO-13). See [testing-and-commissioning.md](testing-and-commissioning.md).
- **Don't:** leave the fridge, the pump or the lighting "outside the RCD" "so it doesn't cut out"; use a 300 mA ID as protection for final circuits.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.14.2.3 (text: "Todos los circuitos terminales deben estar protegidos [...] por un interruptor diferencial de IΔn ≤ 30 mA [...] de actuación no retardada" (all final circuits must be protected [...] by an RCD with IΔn ≤ 30 mA [...] without time delay)); AEA 90364-7-771 Ed. 2006, 771.18.3 (protection against direct contact; same requirement, the 771 is the reference for the 770); Res. ENRE 269/2012 (replacement of item 3.8 and DCI form, note 2), as per [regulations-and-permits.md](regulations-and-permits.md).
### ELEC-PRO-8: In a TT system, protection against indirect contact comes from the RCD (*diferencial*), not the MCB (*térmica*)
- **Rule:** in installations supplied from the public LV network (TT system, mandatory) the only accepted form of automatic disconnection against indirect contact is the **residual current device** (RCD, *disyuntor* / *diferencial*). The MCB (*térmica*) does not fulfill that function. With an ID ≤ 30 mA (or ≤ 300 mA in sections without 30 mA) and earthing resistance Ra ≤ 40 Ω, the touch voltage does not exceed 24 V.
- **Why:** in TT the current of a fault to an exposed conductive part returns through the earth: If = U0 / (Ra + Rn), with Rn the utility's neutral earthing. With Ra = 40 Ω and Rn ≈ 2 Ω: If ≈ 220 / 42 ≈ **5.2 A**; only with very low earth resistances (a few ohms) does it reach a few tens of amperes. A C16 needs 1.45 × 16 = 23.2 A to trip on overload (in less than 1 h) and up to 10 × 16 = 160 A for the instantaneous trip: **it does not break**, and the exposed part stays at about 5.2 A × 40 Ω ≈ **210 V** with respect to earth. The 30 mA ID does break.
- **How:** every exposed conductive part to the PE; PE to the installation's own earth electrode; ID on every part of the installation. Ra values and measurement in [earthing.md](earthing.md).
- **Verify:** measured Ra ≤ the value allowed for the IΔn used (maximum 40 Ω); continuity of the PE up to each socket outlet.
- **Don't:** install an ID "because there is no earth" and consider the matter settled: without PE the exposed part stays energized until someone touches it.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.14.3.2 (TT, RCDs only; 24 V; Ra ≤ 40 Ω) and 770.3.2; AEA 90364-7-771 Ed. 2006, 771.18.4 and 771.3.3.1 (max. Ra raised from 10 to 40 Ω and table of Ra by IΔn, according to the foreword of the 771).

### ELEC-PRO-9: Choose the RCD (*diferencial*) type (AC, A, F, B) by what it will supply
- **Rule:** type AC is only suitable for loads without power electronics. On circuits supplying single-phase electronic equipment (inverter AC or fridge, induction cooktop, washing machine, power supplies, chargers, UPS) use **type A** as a minimum; **type F** if there are single-phase variable-frequency drives; **type B** where there can be smooth DC leakage (electric vehicle charger without DC detection, three-phase drives, photovoltaic inverters that require it). For EV chargers the AEA requires at least type A, 30 mA, one per connection point, and measures against DC leakage.
- **Why:** a leakage with a DC component can prevent a type AC ID from tripping, and smooth DC above 6 mA can "blind" an AC or A device upstream. The AEA itself (770 Ed. 2017) acknowledges that AC is the most used, but the growth of electronic loads makes type A the safe choice.
- **How:**
  - Typical apartment: inverter air conditioners and washing machines (single-phase drive): **type F**, or type A as a minimum if the equipment manufacturer allows it. Kitchen (induction), laundry and socket outlets with electronics: type A. LED lighting and general-purpose socket outlets: **type A recommended**; AC acceptable only if the designer justifies it (the AEA does not prohibit it in the texts read).
  - EV charger (AEA 722:2024, 722.531.2.101): type B ID; or type A + RDC-DD (IEC 62955); or type F + RDC-DD, unless the charging station already includes DC detection. Details in [special-installations.md](special-installations.md).
  - PV inverter and distributed generation (Ley 27.424, user-generator): whatever the inverter manual and AEA 90364-7-712 say (if the inverter does not guarantee separation, type B is usually required); the interconnection protections (anti-islanding, interface protection) are set by the utility as part of the application process. See ELEC-ESP-20 to ELEC-ESP-23 in [special-installations.md](special-installations.md).
- **Verify:** the marking of the ID (waveform symbol or the letter) matches the type in the single-line diagram; the equipment manual does not require a higher type.
- **Don't:** put an AC or A ID upstream of an EV charger that has no DC detection; choose "superinmunizado" (super-immunized) thinking it is type B (it is a variant of type A with higher immunity to high-frequency nuisance tripping).
- **Source:** IEC 61008-1:2024 (covers AC and A; F and B in IEC 62423 together with the 61008 series); AEA 90364-7-722 Ed. 2024, 722.411.3.3, 722.531.2.101 and table 722.I; AEA 90364-7-770 Ed. 2017, note in 770.14.2.3. **Not verified in a primary source:** the numbering 722.531.2.101 in AEA 2024 (it is the one used in [special-installations.md](special-installations.md); in IEC 60364-7-722:2018 the same requirement is in 722.531.3.101 and in IEC 2015 it was 722.531.2.101: confirm which one the AEA adopted); the exact ID type requirement in AEA 90364-7-712 (Ed. 2015) for PV inverters; and whether the 771 or the 770 Ed. 2026 require type A in dwellings (that requirement was not found; IEC 60364-5-53:2019 restricts type AC, the AEA did not adopt this in the texts read).

### ELEC-PRO-10: Size the RCD (*diferencial*) and protect it against overload and short circuit
- **Rule:** the rated current of the ID (25, 40, 63 A...) must be ≥ that of the PIA located in series upstream, or ≥ the sum of the PIAs it supplies downstream. Its own breaking capacity is low (minimum 500 A or 10 In, whichever is greater): there must always be a coordinated short-circuit protective device (PIA or fuse) in the combination guaranteed by the manufacturer (conditional short-circuit current Inc and IΔc ≥ Icc at the point).
- **Why:** the RCD without overcurrent protection (IEC 61008) has no thermal protection: if more current than its rating flows it overheats and is damaged; in a short circuit between phase and neutral its contacts are not made to break thousands of amperes.
- **How:** example: ID 2x40 A supplying PIAs 16 + 16 + 20 A = 52 A → fails by sum; either fit a 2x40 A incoming PIA upstream (meets option "a"), or a 63 A ID. For short circuit: the ID manufacturer's table "protegido por PIA C hasta X A, Inc = 6 kA / 10 kA" (protected by C PIA up to X A). The AEA accepts that it be protected by the downstream PIAs if they are in the same panel built according to the regulations.
- **Verify:** in the single-line diagram, In of the ID ≥ upstream PIA or ≥ downstream sum; manufacturer's sheet with Inc ≥ Icc of the panel. When replacing an ID with one of a different brand, verify again.
- **Don't:** put a 25 A ID as the incoming device of a panel with a 40 A main switch and nothing in between.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.15.2.2.5 (conditions a, b, c, d) and annex 770-B.2.4, table 770-B.X (minimum breaking capacities per IEC 61008: e.g. 500 A for 25 and 40 A; 630 A for 63 A); AEA 771 annex H (equivalent).

### ELEC-PRO-11: Split the circuits among RCDs (*diferenciales*); standing leakage must not exceed ~0.3 IΔn
- **Rule:** the AEA does not set how many circuits go per ID: it allows one ID per circuit or grouping several. Group them so that (a) the sum of the standing leakage of the equipment on one ID does not exceed about 30 % of IΔn (≈ 9 mA for a 30 mA ID) and (b) one trip does not black out the whole apartment or cut the fridge together with an outdoor circuit.
- **Why:** every class I appliance with a filter (PC, TV, power supplies, washing machine, inverter fridge) leaks some current to earth by design (product standards allow on the order of 0.75 to 3.5 mA depending on the type). Added together, plus some damp in an outdoor outlet point (*boca*), they produce trips "for no reason". Splitting into 2 or 3 IDs reduces this and means a fault leaves only part of the installation without supply.
- **How:** (apartment) ID 1: lighting + general-purpose socket outlets in bedrooms/living room; ID 2: kitchen, laundry and air conditioners (type A as a minimum; type F if there are inverter air conditioners or washing machines, ELEC-PRO-9); ID 3 if there is an outdoor area/balcony or a lot of electronic equipment. Combined devices (RCBO) per circuit where maximum continuity is wanted. Example: office with 8 PCs at ~1 mA leakage each = 8 mA on a single 30 mA ID → at the limit; split them in two.
- **Verify:** leakage measurement with a leakage clamp meter (mA) per ID with everything switched on; record it in the test report. The leakage clamp goes around **the circuit's phase and neutral together** (never the PE alone): if it reads anything, that is leakage to earth. It is a live measurement: see "Clamp measurements" at the beginning.
- **Don't:** go up to a 300 mA ID "because it trips"; put the whole installation under a single 30 mA ID in a shop with a lot of equipment.
- **Source:** AEA 90364-7-770 Ed. 2017, note 1 of 770.16.5.4 (one ID per circuit or grouping several); IEC 60364-5-53 (531.3.2, accumulation of protective conductor currents ≤ 0.3 IΔn). **Not verified in a primary source:** the exact IEC subclause number and its equivalent in AEA 90364-5-53; the leakage values per appliance are product standard limits (IEC 60335-1, IEC 62368-1) cited from memory.

### ELEC-PRO-12: Upstream RCD (*diferencial*): only if it protects a line, 300 mA maximum and selective (S)
- **Rule:** when the line between the main panel and the sub-panel (or between sub-panels) needs protection against indirect contact, an ID of up to **300 mA** is allowed, and it is recommended to be **selective (type S, time-delayed)** with respect to the 30 mA ones downstream. For RCD selectivity: upstream IΔn ≥ 3 × downstream IΔn (practical criterion) **and** time delay (type S).
- **Why:** two instantaneous IDs in series (e.g. 40 A/30 mA in the main panel and another 30 mA in the apartment) trip together or the upstream one trips: a fault in a socket outlet cuts everything and forces someone to go down to the meter cabinet. Type S waits long enough for the downstream one to break first.
- **How:** (building) in the meter cabinet, per apartment: two-pole PIA for the sub-main + (if the line uses cables without double insulation or there are exposed conductive parts along the route) 300 mA S ID. In the apartment: instantaneous 30 mA IDs. If the sub-main is class II (sheathed cables or single-core cables in insulating conduit), an upstream ID may not be needed.
- **Verify:** "S" symbol on the front of the upstream ID; test with a tester: when a circuit in the apartment fails, only its own ID trips.
- **Don't:** put an instantaneous 30 mA ID in the main panel and an identical one in the sub-panel; use a 300 mA ID without "S" upstream of the 30 mA ones.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.14.3.2 b) (300 mA maximum, selective recommended, symbol required by IEC 61008/61009) and 770.14.3.1 (class II cables and conduits); IEC 61008-1:2024 4.4.2 (type S); IEC 60364-5-53, 535.3 (selectivity between RCDs in series: non-operating characteristic of the upstream device above the operating characteristic of the downstream one, and upstream IΔn higher than downstream). **Not verified in a primary source:** the exact text of 535.3 (cited from memory) and whether it sets the factor 3; meanwhile, the factor 3 stands as a practical and manufacturers' criterion (the theoretical minimum is 2, because an ID may not trip until 0.5 IΔn and must trip at IΔn).

### ELEC-PRO-13: The test button is pressed at handover and then every month
- **Rule:** at commissioning, the ID is tested with an instrument (current and time) **and** with its button; the user is told to press the button **once a month** and, if it does not trip, to call an electrician.
- **Why:** the button checks that the mechanism has not stuck (IDs that are not operated for years can seize). It does not check the earthing or the tripping time: the tester does that.
- **How:** with the ID closed and live, press "T"; it must open. Reset it. Write the date on the panel label.
- **Verify:** label with the test instruction on the panel (or in the user manual handed over).
- **Don't:** accept an ID as good just because "the button works"; test it with an improvised wire from phase to earth.
- **Source:** AEA 90364-7-770 Ed. 2017, checks in 770.19 (item f, mechanical operation with the push button; item g, test with rated residual current); monthly frequency: manufacturers' instructions (**Not verified in a primary source** (AEA): the AEA text read does not set a frequency). Tests in [testing-and-commissioning.md](testing-and-commissioning.md).

### ELEC-PRO-14: Main switch and incoming switch: a circuit breaker in the main panel, all poles, neutral included
- **Rule:** the **main panel** (TP) has a **circuit breaker** as its incoming device (general isolation and protection; it may have an associated RCD), two-pole with protection on both poles in single-phase, four-pole in three-phase. Each **sub-panel** (TS, *tablero seccional*) has an incoming device with guaranteed isolating capability: switch-disconnector, circuit breaker or ID (IEC 61008/61009). All incoming switches **isolate the neutral**.
- **Why:** the main switch protects the sub-main and allows the whole property to be switched off in a single movement; if it does not break the neutral, a polarity reversal or a live neutral (broken neutral upstream) leaves parts live with everything "off".
- **How:** in the 770 the main switch cannot exceed 63 A; if more is needed, the 771 applies. If a single sub-main leaves the main switch, that device protects it; if several leave, it is general protection and each outgoing line has its own. Location and clearances in [panels.md](panels.md); the building in [buildings.md](buildings.md).
- **Verify:** with the main switch open there is no voltage on any output terminal (neither phase nor neutral with respect to earth).
- **Don't:** use a switch without a trip (isolator) as the main switch in the main panel; break only the neutral with a device.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.16.5.1, 770.16.5.3 and 770.16.5.4; AEA 90364-7-771 Ed. 2006, 771.20.5.

### ELEC-PRO-15: Neutral protection: never alone, protected if it is smaller or if there are harmonics
- **Rule:** in single-phase the neutral is broken and protected together with the phase (ELEC-PRO-1). In three-phase with neutral: if the neutral has the same cross-section as the phases, it does not need its own overcurrent protection, **unless** the 3rd harmonic content exceeds about 33 %: then the neutral is sized for its actual current and has its own overcurrent detection. If the neutral is **smaller**, it needs protection suited to its cross-section. Never fit a fuse or a switch that breaks only the neutral.
- **Why:** with unbalanced loads or with many electronic loads (switch-mode power supplies, LED, PCs) the 3rd-order harmonic currents add up in the neutral and can equal or exceed the phase current; a reduced neutral overheats without anything detecting it. An open neutral with the phases connected is the cause of the overvoltages in ELEC-PRO-19.
- **How:** in common services and offices with a lot of electronics, neutral of the same cross-section as the phases and a four-pole PIA with 4 protected poles or with protected neutral. Recommended imbalance between phases ≤ 30 %.
- **Verify:** neutral cross-section in the single-line diagram; clamp measurement of the neutral current with the typical load (live measurement, trained person; see "Clamp measurements" at the beginning). If the neutral carries as much current as a phase or more, there are harmonics: review cross-section and protection.
- **Don't:** reduce the neutral of a three-phase line that supplies apartments or offices to save copper.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.16.5.4 (equal or reduced neutral, 30 % imbalance); IEC 60364-4-43, 431.2.3 (overcurrent detection in the neutral when harmonics may exceed its capacity); IEC 60364-5-52 annex E (factors for 3rd harmonic: above ~33 % the neutral current governs). **Not verified in a primary source:** IEC numbering and thresholds cited from memory; equivalent in AEA 90364-4-43 / 90364-5-52 Ed. 2006.
### ELEC-PRO-16: SPD (*DPS*): mandatory with a lightning protection system, or with an overhead network in an area with more than 25 thunderstorm days per year
- **Rule:** installing transient overvoltage protection devices, SPD (*DPS*), is **mandatory** when: (a) the building has an external lightning protection system (*pararrayos*, lightning rod), whatever the area; (b) the building is supplied at LV (BT) by a fully or partly **overhead** network and the keraunic level exceeds **25 thunderstorm days per year**. With a fully underground network it is not mandatory, but it may be advisable depending on the risk analysis.
- **Why:** nearby lightning strikes and switching operations induce spikes of thousands of volts that damage electronics and insulation; the cost of an SPD is low compared with the cost of the equipment in a building.
- **How:** take the keraunic level from the maps in AEA 92305-11; the exception for case (b) requires a risk analysis according to AEA 92305-2. The overhead-network rule does not apply if the line uses insulated conductors with an earthed screen or includes an earthed conductor. A 4-story building with a lightning protection system → SPD mandatory **in the main panel (TP) of each installation**: the common services panel (type 1+2) **and** the panel of each unit (type 2, coordinated with the type 1). In a building with grouped meters there is no user "main" switch upstream of all the meters (the busbars in the meter cabinet belong to the utility (distribution company), unmetered energy): an SPD in common services protects only the elevator, pumps and landing (hallway), not the apartments (*depto*).
- **Verify:** in the design report (*memoria*): network type, keraunic level, whether there is a lightning protection system, and the decision taken.
- **Don't:** treat the lightning protection system as protection for the internal installation: without an SPD, the lightning protection system increases the overvoltages inside the building when it is struck.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.15.4 and table 770.15.III; AEA 90364-7-771 Ed. 2006 (Viviendas, oficinas y locales unitarios: dwellings, offices and single shops), 771.19.4 (table of SPD installation conditions, cited as table 771.19.III in the technical literature); AEA 90364-4 section 443 and 90364-5 section 534 (Ed. 2006); AEA 92305-2 and 92305-11 (2015/2016).

### ELEC-PRO-17: Choose the SPD (*DPS*) by type, protection level (Up), operating voltage (Uc) and discharge current
- **Rule:** type 1 (tested with a 10/350 µs wave, Iimp) at the origin when there is a lightning protection system or the service drop is overhead and exposed; type 2 (8/20 µs wave, In ≥ 5 kA) in the main panel or sub-panels; type 3 near sensitive equipment located more than about 10 m from the type 2. Up of the assembly ≤ 2.5 kV to protect category II equipment (appliances, electronics), and lower the more sensitive the protected equipment is. Maximum continuous operating voltage: in TT, **Uc ≥ 1.1 U0 = 1.1 × 220 = 242 V** between phase and neutral and between phase and PE (between neutral and PE, Uc ≥ U0); in practice **255-275 V** is used to leave a margin over the network (220 V + 8 % = 237.6 V).
- **Why:** each type handles a different energy; a type 2 alone cannot withstand the partial current of a direct strike on the lightning protection system. If Uc is low, the SPD conducts during normal network overvoltages and is destroyed or trips the ID (RCD, *disyuntor* / *diferencial*).
- **How:**
  | Type (IEC 61643-11) | Test wave | Where | Indicative value |
  |---|---|---|---|
  | Type 1 (class I) | Iimp 10/350 µs | Origin, with lightning protection system | Iimp ≥ 12.5 kA per pole for protection level III/IV (more for levels I/II) |
  | Type 2 (class II) | In 8/20 µs | Main panel / sub-panel | In ≥ 5 kA |
  | Type 3 (class III) | Combination wave | Next to the equipment | Per manufacturer |
  If there are type 1 and type 2 devices of different brands, respect the manufacturer's coordination distance (around 10 m of cable) or use coordinated/combined T1+T2 products.
  - **Broken (lost) neutral (*corte de neutro*, temporary overvoltage, TOV):** with the neutral broken, the phase-neutral voltage can approach 380 V for minutes (ELEC-PRO-19). That exceeds any Uc of 275 V: the varistor conducts continuously and is destroyed, or it trips the ID or the backup protection. Choose an SPD that declares its TOV withstand (UT) according to IEC 61643-11 and, in buildings or networks at risk of a broken neutral, combine it with the permanent overvoltage protector of ELEC-PRO-19, which opens first. An SPD burned out after a broken neutral does **not** indicate lightning (see ELEC-DIA-7 and ELEC-DIA-14 in [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Verify:** SPD data sheet: type, Uc, Up, In/Iimp, connection scheme (TT), required backup protection, end-of-life indicator.
- **Don't:** compare SPDs of different types by "maximum kA" (Imax): the test waves are different and the numbers are not comparable.
- **Source:** IEC 61643-11 (types/classes and waves); IEC 60364-4-44 section 443 and IEC 60364-5-53 section 534 / AEA 90364-4-443 and 90364-5-534 (Ed. 2006); Legrand SPD guide (In 5 kA minimum for type 2; Iimp 12.5 kA/pole for LPL III/IV; overvoltage that can double beyond 10 m); IEC 60364-5-53, table of minimum Uc by earthing system (TT: 1.1 U0 between L-N and L-PE, U0 between N-PE; table 53C in the 2001 edition, table 534.2 in the 2015 revision) and requirement for coordination with temporary overvoltages. **Not verified in a primary source:** the table number in AEA 90364-5-534 Ed. 2006 and the IEC text (cited from memory); 255-275 V is market practice.

### ELEC-PRO-18: Mount the SPD (*DPS*) with short leads, backup protection and on the correct side of the RCD (*diferencial*)
- **Rule:** the SPD connection leads, **as short as possible**: the standard recommends that the sum of the lengths from the connection point on the line, through the SPD and its protection, to the earth bar should not exceed **0.5 m**; if that is not possible, use a V connection (incoming and outgoing on the same SPD terminals) or an SPD with a lower Up. The SPD gets the backup protection (fuse or PIA (MCB, *térmica*)) specified by its manufacturer. In TT, if the SPD goes upstream of the main ID, use the "CT2" connection (varistors between phase and neutral + gas discharge tube between neutral and PE, "1+1" or "3+1"); if it goes downstream of an ID, prefer that ID to be type S.
- **Why:** each meter of lead adds around 1 kV of inductive drop during the impulse: with long leads the equipment receives much more than the SPD's Up. Without backup, an SPD that reaches end of life in short circuit burns the panel. In TT upstream of the ID, a faulty phase-to-PE varistor would leave a permanent leakage with nothing to cut it off.
- **How:** SPD next to the main switch, SPD PE straight to the main earth bar (which should preferably enter through the main panel); SPD connection conductor to the PE / earth bar: minimum **6 mm² Cu for type 2** and **16 mm² Cu for type 1** (IEC 60364-5-53, 2015 revision of section 534, 534.4.10; AEA 90364-5-534 Ed. 2006, based on IEC 2001, allowed 4 mm² for type 2): use 6 mm² as the floor, or more if the manufacturer's sheet asks for it; leave the status indicator visible.
- **Verify:** measure with a tape: L1 + L2 + L3, target ≤ 0.5 m (manufacturer example: 20 cm + 10 cm = 30 cm ✔); if it is more, record why and what was done (V connection, lower Up). Status indicator green.
- **Don't:** put the SPD on a rail far from the earth bar "because there was no room"; replace a spent SPD with one of a different Uc without checking the sheet.
- **Source:** IEC 60364-5-53 section 534 (2015 revision: 534.4.8 connection length, "preferably" ≤ 0.5 m; 534.4.10 minimum cross-sections; backup; CT1/CT2 configurations); Schneider guide "¿Cómo seleccionar la protección contra sobretensiones?" (How to select overvoltage protection?) (50 cm rule); AEA 90364-7-770 Ed. 2017, 770.14.4.4 (bringing the earth conductor in through the main panel helps overvoltage protection). **Not verified in a primary source:** the subclause numbers and the 6/16 mm² cross-sections of IEC 2015 (cited from memory, they match SPD manufacturers' guides); the equivalent in AEA 90364-5-534 Ed. 2006.

### ELEC-PRO-19: Permanent overvoltages from a broken neutral (*corte de neutro*): voltage protector in buildings and three-phase networks
- **Rule:** where several single-phase units are fed from a three-phase network with a common neutral (buildings, neighborhoods with an overhead network), install in **each unit** (main panel or sub-panel of each apartment) an **over- and undervoltage protector** (voltage protector, *protector de tensión*) that disconnects the installation when the voltage leaves a range. AEA presents it as "altamente recomendable" (highly recommended) and at the designer's discretion, not as mandatory. A protector in common services protects only common services.
- **Why:** if the neutral is broken upstream (in the network, in the service connection, in the riser (*montante*)), the units connected to the less loaded phase can receive voltages approaching 380 V and burn everything plugged in; those on the more loaded phase are left at low voltage (motors and compressors suffer). An SPD does **not** protect against this: it is an overvoltage that lasts minutes, not microseconds.
- **How:**
  - Permitted LV supply voltage in the Edenor/Edesur area: 220 V ± 8 % (202.4 to 237.6 V), Subanexo 4 of the 2025-2030 period. Outside that area, your utility's concession contract and the rules of the provincial regulator govern (EPRE Mendoza, ERSeP Córdoba, OCEBA in Buenos Aires province; in Santa Fe, the EPE regulations, etc.): look up their tolerance before setting. Set the trip above the band with a margin to avoid nuisance disconnections: practical criterion, overvoltage around 250-260 V and undervoltage around 175-185 V, with reconnection after 1 to 3 minutes (protects refrigerator and AC compressors).
  - How it is linked to the disconnection (choose depending on whether you want automatic reconnection):
    | Option | Setup | Reconnects by itself | Watch out for |
    |---|---|---|---|
    | A. Voltage relay + contactor | The relay opens the coil of the contactor, which is in series with the main switch | Yes, time-delayed | Two-pole contactor (phase and neutral), AC-1 ≥ In of the main switch |
    | B. Relay + **shunt** trip coil (MX, "shunt trip") on the main PIA | The relay energizes the coil, which trips the PIA | No: manual reset | The coil needs voltage to trip: feed it as the manufacturer indicates (usually from the output of the PIA itself) and choose one whose range withstands 380 V |
    | C. **Undervoltage** coil (MN) on the PIA | The PIA opens when the voltage drops; with a relay, also on overvoltage | No: manual reset | Opens with every network outage: after a power cut someone has to go and switch the main back on (annoying in an apartment, useful where automatic restart is not wanted) |
    | D. POP protector (IEC 63052) | Modular device with its own switching, in series | Depends on model | Rating ≥ In of the main switch |
    | E. Plug-in protector | Only for one appliance | Yes | Does not protect the installation |
  - Any option: the device must **withstand without damage the phase-to-phase voltage (380 V)** that appears with a broken neutral; check that figure on the sheet (maximum permitted overvoltage).
  - In the building, also: main line neutral without doubtful splices, tight terminals (see [buildings.md](buildings.md) and [reviewing-a-panel.md](reviewing-a-panel.md)).
- **Verify:** test the protector with its test function (if it has one) and write the set thresholds on the panel.
- **Don't:** believe that the SPD or the RCD protects against a broken neutral; set the overvoltage at 240 V or less (disconnections every time the network rises within normal limits).
- **Source:** AEA 90364-7-770 Ed. 2017, 770.13.1 b) (permanent overvoltages "altamente recomendables", highly recommended) and 770.15.5 (at the designer's discretion); AEA 90364-7-771 Ed. 2006, 771.19.5 (permanent overvoltages) and 771.19.6 (undervoltages); Res. ENRE 303/2025 (Edesur, art. 15) and 304/2025 (Edenor, art. 16), Subanexo 4 "Normas de calidad del servicio público y sanciones" (public service quality standards and penalties) period 2025-2030, item 2 (technical product quality: permitted variation in MV and LV −8 % / +8 %, according to the reading done for [troubleshooting-common-cases.md](troubleshooting-common-cases.md)); it replaced Subanexo 4 of Res. ENRE 63/2017 (Edenor) and 64/2017 (Edesur), period 2017-2021; IEC 63052:2019 (POP); manufacturers' catalogs of PIA auxiliaries (MX and MN coils). **Not verified in a primary source** in this revision: the text of Subanexo 4 2025-2030 (the official PDF could not be extracted) and the tolerance of each provincial regulator. The trip settings are a practical criterion, **not** a value from a standard.

### ELEC-PRO-20: Fuses: the utility's NH fuses are not touched; in dwellings and offices they are not used as circuit protection
- **Rule:** in dwellings and offices AEA does not accept the fuse as a protective device for the user's installation; it does accept it in premises with permanent presence of instructed or skilled personnel (BA4/BA5). A common services panel in a residential building is **not** BA4/BA5 by default (the person in charge of the building (*encargado*) opens it): for fuses there, check AEA 90364-7-772 Ed. 2019 and the design (**Not verified in a primary source** that it allows them). The NH fuses in the utility service box (*caja de toma*) or in the isolation box (*caja de seccionamiento*) belong to the utility: they are not replaced or bypassed.
- **Why:** changing a fuse requires handling parts that may remain live and choosing the right rating; the ordinary user ends up putting in "a wire". With gG fuses, I2 = 1.6 In, so the second overload condition is **not** met automatically.
- **How:** (where allowed) gG fuse (general purpose) for cables; aM only as short-circuit backup for motors. Check 1.6 In ≤ 1.45 Iz → **In ≤ 0.9 Iz**. Example: cable with Iz = 100 A → In ≤ 1.45 × 100 / 1.6 = 90.6 A → standard gG fuse of **80 A** (not 100 A). Fuse base with on-load isolation or off-load operation depending on the type; fuse pullers and PPE.
- **Verify:** in the single-line diagram (*unifilar*): type (gG/aM), size (NH 00, 1, 2, 3), In and breaking capacity; In ≤ 0.9 Iz.
- **Don't:** replace an NH fuse "because it blew" without finding the cause; put a fuse in the neutral; tamper with the utility service box.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.20 (according to its foreword: "No se admite el fusible como dispositivo de protección en viviendas y oficinas, permitiéndoselo en cambio en los locales con presencia permanente de personal instruido o calificado" (the fuse is not accepted as a protective device in dwellings and offices, but it is allowed in premises with permanent presence of instructed or skilled personnel)); APSE, Ingeniería Eléctrica Nov 2015 (I2 = 1.6 In for gG according to IEC 60269); Edenor service connection diagrams published in Ingeniería Eléctrica Dec 2017 (utility service box with size 1 NH bases, isolation box with size 3 NH, supplied by the utility).

### ELEC-PRO-21: Selectivity (*selectividad*): the protection closest to the fault must trip
- **Rule:** design the protection chain (main switch → sub-main → sub-panel → circuits) so that on an overload or short circuit only the device immediately upstream of the fault opens.
- **Why:** without selectivity (discrimination), a short circuit in a socket outlet on the 3rd floor can open the apartment's main switch (or, if it is in a common circuit, the common services main switch), or blow the utility's fuse (ELEC-PRO-29), and leave without service people who do not have the fault (in common services: elevator, pumps, stairway lighting).
- **How:**
  - **Overload (current selectivity):** a rating ratio ≥ 2 between the upstream and downstream PIA is a practical criterion (e.g. 40 A upstream, ≤ 20 A downstream); with PIAs of the same curve and a small ratio (25 / 20 A), there is no selectivity.
  - **Short circuit:** between modular PIAs selectivity is usually only partial (up to a certain current); the value comes from the **manufacturer's selectivity tables** for that exact combination. It improves with a D curve incoming PIA or a selective breaker/molded case breaker upstream.
  - **gG fuses with each other:** rated current ratio ≥ 1.6 (IEC 60269 criterion for gG).
  - **RCDs:** ELEC-PRO-12.
  - **Building (common services):** the pump or the elevator should have its own PIA and motor protection, and the common services main switch should not be the first to trip.
- **Verify:** in the single-line diagram, for each pair in series, the manufacturer's table or the overlay of time-current curves.
- **Don't:** mix brands and "assume" selectivity or cascading (*filiación*) without a table; put a main switch of the same rating, or only slightly higher, as the largest final circuit (e.g. main 2x32 A with a TUE of 2x32 A): on an overload or a short in that circuit both can trip. The main switch is not the sum of the circuits (16 + 16 + 20 + 20 + 32 = 104 A): it comes from the demand (grade, DPMS (maximum simultaneous power demand)) and from the Iz of the sub-main.
- **Source:** AEA 90364-7-772 Ed. 2019 (common services; panel diagrams and pump room examples in its annex C); IEC 60364-5-53 (coordination of devices); **Not verified in a primary source:** the 2:1 ratio between PIAs is a practical criterion; the 1.6 ratio between gG fuses is from IEC 60269-1 cited from memory.
### ELEC-PRO-22: Only certified materials with guaranteed data
- **Rule:** PIAs (MCBs, *térmicas*), IDs (RCDs, *disyuntor* / *diferencial*), combined devices, SPDs (*DPS*), isolators (*seccionador*), socket outlets and cables must have a current conformity assessment (certification mark on the product or on the packaging) and a data sheet with the figures used for coordination (breaking capacity, energy limiting class, I²t, Inc of the ID, Up/Uc of the SPD).
- **Why:** without guaranteed data you cannot verify ELEC-PRO-3, -5, -10 or -21; and counterfeit or untested devices tend to fail exactly during the short circuit.
- **How:** the current national regime for "materiales para instalaciones eléctricas" (materials for electrical installations) (up to 63 A, except cables) is Res. SIyC 236/2024 (with the Annex II set by Res. SIyC 26/2025: PIA IEC 60898-1 in item 4.5.2, ID IEC 61008-1 in 4.5.3, combined devices IEC 61009-1 in 4.5.4, SPD in 4.5.14, fuses in 4.5.16; see [iram-standards.md](iram-standards.md) ELEC-IRA-2 and ELEC-IRA-7) + Disposición DNRT 2/2025 + conformity marking (Res. SIyC 237/2024 and Providencia DNRT of 2025-10-30), with certification schemes 1b or 5 for manual switches, thermal-magnetic breakers, RCDs, combined devices, SPDs and isolators. Details of the regime in [regulations-and-permits.md](regulations-and-permits.md).
- **Verify:** certification mark and standard on the device; data sheet kept with the design report (*memoria*).
- **Don't:** buy MCBs or RCDs online without a certification mark; combine a PIA of one brand with an ID of another without the coordination table from the ID manufacturer.
- **Source:** same chain as [regulations-and-permits.md](regulations-and-permits.md) (ELEC-NOR-14): Res. SIyC 236/2024 (2024-08-29), Res. SIyC 26/2025 (BO 2025-02-25, replaces Annex II of 236/2024 with IF-2025-17295098-APN-DNRT#MEC; read in full according to [iram-standards.md](iram-standards.md) ELEC-IRA-2) and Res. SIyC 237/2024; Disposición DNRT 2/2025 (BO 2025-04-15) and its annex; Providencia DNRT PV-2025-120654504 (conformity marking, 2025-10-30); Res. SIyC 16/2025 (repeals Res. 169/2018). Annex of Disp. 2/2025: item 2.e (exclusion of materials above 63 A except cables) and item 5.2.3 (schemes 1b or 5), as in ELEC-NOR-14 and ELEC-IRA-2.

### ELEC-PRO-23: Arc fault detection device (AFDD): recommended, not mandatory
- **Rule:** AEA recommends (does not require) arc fault detection devices (AFDD, IEC 62606) in main panels and sub-panels of dwellings; consider them in premises with fire risk, old cables, or where people sleep.
- **Why:** a series arc at a loose terminal or a crushed cable draws few amperes: neither the MCB nor the RCD sees it, and it is a frequent cause of fires.
- **How:** AFDD per circuit or combined AFDD+PIA(+ID), depending on the manufacturer; it takes up space in the panel: plan the spare space.
- **Verify:** AFDD test button and its indicator.
- **Don't:** use it as an excuse not to retighten terminals: correct tightening with torque comes first.
- **Source:** AEA 90364-7-770 Ed. 2017, note at the end of 770.16.5.4 ("se recomienda la instalación de dispositivos para detección de arcos eléctricos AFDD", the installation of AFDD arc fault detection devices is recommended).

### ELEC-PRO-24: Common services motors (pumps, elevator): motor protection in addition to the PIA (MCB, *térmica*)
- **Rule:** each fixed common services motor gets, in addition to the circuit protection (PIA or fuse), **motor overload protection** (motor protection circuit breaker (*guardamotor*), or contactor + thermal overload relay) set to the nameplate current and coordinated with the short-circuit device. Three-phase pumps also get protection against **phase loss** (and a phase sequence relay if reverse rotation damages the pump) and against **dry running** (float switch, electrodes or level relay in the cistern). The elevator gets whatever its manufacturer requires.
- **Why:** the circuit PIA protects the cable, not the motor: a stalled motor or one running on two phases draws somewhat more than its rated current and burns out without the PIA tripping. A pump running dry is destroyed in minutes. The variable frequency drive of the elevator or the booster pump generates leakage with a DC component (ELEC-PRO-9).
- **How:**
  - **Motor protection circuit breaker** (IEC 60947-2 / 60947-4-1) set to the nameplate In, trip class 10 for normal starts, with phase-loss sensitivity.
  - **Coordination with the contactor (IEC 60947-4-1):** type 1 = after a short circuit the starter may be left unusable (with no risk to people); type 2 = it remains fit for further use, with at most slightly welded contacts that separate easily. For the building's pumps ask for **type 2** (manufacturer's table for the exact combination of motor protection circuit breaker/fuse + contactor).
  - **Booster pump:** starts many times per hour: a well-sized hydropneumatic tank or a variable frequency drive; with a drive, ID type F or B according to the manual.
  - **Elevator:** dedicated circuit with a lockable disconnect in the machine room; ID type (A, F or B depending on the drive), rating and cross-section are given by the manufacturer (ELEC-EDI-13 in [buildings.md](buildings.md)).
  - **RCD (*diferencial*):** the pump room is damp: 30 mA ID for socket outlets and lighting; for the motive power, the ID the equipment manufacturer allows, coordinated with the incoming one (ELEC-PRO-12).
- **Verify:** motor protection circuit breaker set to the nameplate current (not "at maximum"); simulate an empty cistern and a full tank; with the motor running, current with a clamp meter compared with the nameplate (live measurement, trained person); phase sequence with a phase rotation meter before coupling (ELEC-MED-7).
- **Don't:** protect a three-phase pump only with a four-pole PIA; set the motor protection circuit breaker well above the nameplate "because it kept tripping"; bypass (jumper) the cistern float switch.
- **Source:** IEC 60947-4-1 (starters and type 1 / type 2 coordination); IEC 60947-2 (motor protection circuit breakers as circuit breakers); AEA 90364-7-772 Ed. 2019 (dedicated circuit per elevator and per pump system; figure 772.C.7 pump room), according to [buildings.md](buildings.md) (ELEC-EDI-13, ELEC-EDI-14); ELEC-ESP-14 in [special-installations.md](special-installations.md). **Not verified in a primary source:** that 772 requires a motor protection circuit breaker, phase-loss relay or type 2 coordination (they are good design practice).

### ELEC-PRO-25: Each circuit's neutral goes through the same RCD (*diferencial*) as its phase; the PE never goes through the RCD
- **Rule:** each circuit takes its neutral **from the output of the same ID** that feeds its phase. The protective conductor (PE) **never** goes through the ID. Neutral and PE are not joined at any point of the user's installation (TT system): not in the panel, not in a socket outlet, not inside an appliance.
- **Why:** the ID compares the current going out on the phase with the current returning on the neutral. If a circuit's neutral is taken from another group or from before the ID, the current returns "outside" and the ID sees a false leakage: it trips when the load is switched on. If the neutral touches the PE (an N-PE jumper in a socket outlet "so it has earth", an appliance with damaged insulation between N and the frame), part of the neutral current returns through earth and the ID trips. It is the number one cause of ID tripping on site.
- **How:** neutral terminal block **per ID**, labeled; one neutral per circuit; PE to its own bar. To find a mixed neutral or an N-PE jumper: dead (no voltage), disconnect the circuit's neutrals in the panel and measure N-PE insulation with a megohmmeter (megger) (ELEC-DIA-4, ELEC-DIA-5 and ELEC-DIA-9 in [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Verify:** in the panel, each neutral comes from its ID's terminal block; N-PE insulation of each circuit ≥ 1 MΩ with appliances unplugged; trip test with the tester.
- **Don't:** take the neutral of a new circuit "from the bar that is nearby"; join the socket outlet's earth terminal to the neutral; run the PE through an ID terminal.
- **Source:** ID operating principle (IEC 61008-1); AEA 90364-7-770 Ed. 2017, 770.16.5.1 (two-pole disconnection) and 770.14.3.2 (TT); ELEC-TAB-16 in [panels.md](panels.md). **Not verified in a primary source:** an AEA clause that says it literally; the rule follows from the ID principle and the TT system.

### ELEC-PRO-26: Old installation (plug fuses (*tapones*), knife switch, single-pole MCBs (*térmicas*)): what to replace and what to do in the meantime
- **Rule:** when renovating, screw-in fuses (plug fuses, Diazed) and porcelain fuses, knife switches and single-pole PIAs are replaced by a panel with two-pole PIAs per circuit (ELEC-PRO-1) and 30 mA IDs (ELEC-PRO-7), and the PE is added. If the renovation is not done right away, the minimum measure is a **two-pole 30 mA ID at the incoming end, protected by a two-pole PIA** suited to the line, and bringing the PE to the socket outlets of the most used class I appliances (refrigerator, washing machine, water heater).
- **Why:** the fuse gets "fixed" with wire and then protects nothing; the knife switch leaves live parts exposed; the single-pole device may end up on the neutral and leave the phase connected. The ID is the improvement with the greatest effect for the time and cost; without PE, the exposed conductive part stays live until someone touches it (ELEC-PRO-8).
- **How:** survey first (insulation per circuit, dead); if the ID trips when installed, there are leakages to find (ELEC-DIA-4), not "an oversensitive ID". While fuses remain: rating according to the cable cross-section (ELEC-PRO-4 and ELEC-PRO-20: In ≤ 0.9 Iz for gG), never wire. Order of priorities in ELEC-DIA-17 ([troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Verify:** ID tested with a tester; no fuse with wire or with a rating higher than the cable allows; PE with continuity where it was installed.
- **Don't:** replace a fuse with a bigger one; install three-pin socket outlets with no PE behind them; change fuses or a knife switch live (an open knife switch is still live on the incoming side).
- **Source:** AEA 90364-7-771 Ed. 2006 (foreword: the fuse is not accepted as protection in dwellings and offices; two-pole disconnection); AEA 90364-7-770 Ed. 2017, 770.14.2.3 and 770.16.5.1. **Not verified in a primary source:** an Argentine standard that sets minimum measures for existing installations; the minimum measure is a technical risk criterion, as in ELEC-DIA-17.

### ELEC-PRO-27: Generator set: changeover switch that disconnects phase and neutral, and protection designed for its low short-circuit current
- **Rule:** the generator set (*grupo electrógeno*) is connected only through a changeover switch (manual I-0-II, or automatic with mechanical and electrical interlocking) that separates **phase and neutral** from the network before connecting the generator: the network must **never** be back-fed (it electrocutes utility staff working on the line). Downstream of the changeover switch, the installation remains protected by its PIAs and its 30 mA ID, and the generator neutral is referenced to earth so that the ID works.
- **Why:** besides the risk to third parties, a small generator delivers a low short-circuit current (a few times its rated current and for a short time): a C or D curve PIA may not trip instantaneously with the generator, although it does with the network.
- **How:** changeover switch rated ≥ In of the main switch, after the meter and before the main panel; PIA at the generator output suited to its rated current; check the instantaneous tripping of the circuits with the generator's Icc (manufacturer's data) and, if it does not work out, use a B curve or rely on the ID for protection of persons. Neutral and earth in ELEC-ESP-25 and ELEC-ESP-26 ([special-installations.md](special-installations.md)); safety in ELEC-SEG-21 ([site-safety.md](site-safety.md)).
- **Verify:** with the changeover switch in "grupo" (generator), there is no generator voltage at the network terminals; ID test with the generator running and the network disconnected.
- **Don't:** the cable with two male plugs; a changeover switch that disconnects only the phase; switching off only the main MCB (*térmica*) instead of using a changeover switch.
- **Source:** IEC 60364-5-55, clause 551 (LV generating sets; basis of AEA 90364-5-55 Ed. 2006), according to ELEC-ESP-25/26 and ELEC-SEG-21. **Not verified in a primary source:** the AEA text of 551; the Icc of small generators is manufacturer data and varies a lot by model (inverter units give very little).

### ELEC-PRO-28: Busbar combs (*peines*), terminals and temperature: the PIA heats up too
- **Rule:** (a) busbar combs or connecting bars between PIAs are used within their current-carrying capacity and are of the **same brand and series** as the devices; (b) all terminals are tightened to the manufacturer's **torque** and retightened during maintenance; (c) take into account the **current derating** of PIAs at high ambient temperature and when mounted side by side (full panels, in the sun, next to contactors or power supplies).
- **Why:** a comb of another brand does not seat well in the terminal and heats up; a loose terminal is a series arc and a fire (ELEC-DIA-11); the PIA is calibrated at 30 °C and in a panel at 40-50 °C its thermal threshold drops: it trips "for no reason" with loads close to its rating.
- **How:** comb current according to the catalog (feeding it from the center splits the current between the two halves); cables with a ferrule or suitable lug; torque around 2 to 3 N·m on modular PIA terminals (the exact value is on the device or its sheet); leave a free module or a spacer between heavily loaded devices; with the temperature and side-by-side mounting factors from the manufacturer's sheet, correct the effective In when Ib is close to In (see the example in ELEC-PRO-4).
- **Verify:** torque screwdriver at handover; thermography under load (from a distance, without opening live parts) or a touch check **only after switching off and verifying absence of voltage**, looking for hot devices or terminals; comb and PIAs of the same series.
- **Don't:** mix brands on the same comb; leave the cut end of a comb without its cap; put two cables of different cross-section in the same terminal if the manufacturer does not allow it.
- **Source:** data sheets from manufacturers of PIAs and combs (comb current, torque, correction curves for temperature and side-by-side mounting); IEC 60898-1 (calibration reference temperature 30 °C). **Not verified in a primary source:** the torque and correction values (they depend on each product; around 0.9-0.95 In at 40-50 °C according to catalogs).

### ELEC-PRO-29: Coordination with the utility's fuse (selectivity toward the network)
- **Rule:** the main switch of each unit and the common services main switch must open **before** the upstream utility (distribution company) fuse (NH in the utility service box (*caja de toma*) or isolation box (*caja de seccionamiento*), or the meter protection). Ask for the rating and type of that fuse and verify selectivity (discrimination).
- **Why:** if the NH fuse blows on a short in the sub-main, other units (or the whole building) are left without power and you have to wait for the utility to replace it; the user cannot touch it (ELEC-PRO-20).
- **How:** for overload, a fuse / PIA rating ratio ≥ 1.6 to 2 as a practical criterion (e.g. 40 A main PIA with an 80 A gG fuse or higher). For short circuit, PIA-fuse selectivity holds up to a certain current and comes from the **PIA manufacturer's table** against gG fuses of each rating (the total I²t of the PIA must stay below the pre-arcing I²t of the fuse). The rating of the main switch also cannot exceed what the service connection and the contracted power allow.
- **Verify:** in the design report: rating of the utility's fuse, In of the main switch, and the selectivity table used.
- **Don't:** install a main switch with a rating equal to or greater than the utility's fuse; "test" selectivity by causing a short.
- **Source:** IEC 60269-1 (characteristics of gG fuses); manufacturers' PIA-fuse selectivity tables; Edenor service connection diagrams (Ingeniería Eléctrica Dec 2017). **Not verified in a primary source:** the fuse ratings each utility uses per supply type; the 1.6-2 ratio is a practical criterion.

## Example case: 4-story building, single-phase apartments
Typical scheme (the actual design is defined by the professional and the utility; see [buildings.md](buildings.md) and
[panels.md](panels.md)). Three-phase supply 3x380/220 V to the building, single-phase 220 V apartments (*depto*) spread across
the three phases, three-phase common services.

| Point | Protection | Criterion | Rule |
|---|---|---|---|
| Utility service box / isolation box (utility) | Utility's NH fuses | The installer does not touch them; the main switch of each unit must be selective with them | ELEC-PRO-20, -29 |
| Busbars and meter cabinet (utility) | None belonging to the user: unmetered energy, sealed | Not touched, and no user devices are installed. There is no user "main" switch that disconnects the whole building | ELEC-PRO-20; ELEC-EDI-5 |
| Common services main panel (after its three-phase meter) | Four-pole switch with neutral, short-circuit breaking capacity (PdCcc) ≥ reported Icc (generally ≥ 10 kA if there is a nearby transformer); type S ID upstream of the 30 mA ones; SPD type 1+2 if there is a lightning protection system; voltage protector for elevator and pumps | Disconnects **common services** (not the apartments); protects its line; overvoltages | ELEC-PRO-3, -12, -14, -16 to -19 |
| Common services sub-panels | Elevator and pumps: PIA + motor protection circuit breaker/contactor, phase loss, level (ELEC-PRO-24). Landing and stairway: PIA + 30 mA ID, stairway timer switch or sensor suitable for the LED load (inrush peak). Self-contained emergency lights: fed from the lighting circuit they cover, after its PIA and its ID, so they turn on when that circuit is cut (design criterion) | A fault in the pump must not turn off the stairway | ELEC-PRO-21, -24; ELEC-EDI-12 to -16 |
| Main panel of each apartment (next to the meter, in the meter cabinet) | Two-pole PIA, e.g. C 2x40 A, PdCcc ≥ Icc at the cabinet (≥ 6 kA if no data); optional 300 mA type S ID if the line requires it. **Replacing it requires a disconnection by the utility**: its incoming terminals remain live (see "Safety first") | Protects the sub-main (e.g. 2x10 mm² + PE) | ELEC-PRO-3, -4, -12, -14 |
| Sub-main to the floor | Cable sized by Iz, voltage drop and short circuit. One conduit per line (ELEC-EDI-7); if several lines share a raceway, grouping factor: 10 mm² × 0.7 = 50 × 0.7 = 35 A does **not** allow C40 → 16 mm² (66 × 0.7 = 46.2 A ≥ 40 A ✔) or each line in its own conduit | In of the main PIA ≤ corrected Iz | ELEC-PRO-4, -5 |
| Apartment sub-panel | Incoming: two-pole switch-disconnector or two-pole PIA; 2 or 3 30 mA IDs (kitchen/laundry type A; ACs and inverter washing machines type F; lighting and general-purpose socket outlets type A recommended); SPD type 2 coordinated with the common services T1 (mandatory if the building has a lightning protection system); over/undervoltage protector **per apartment** (here or in the main panel) | Disconnection of the apartment; RCD by groups; DCI (ID ≤ 30 mA, note 2 of the form) | ELEC-PRO-7, -9, -10, -11, -14, -16 to -19 |
| Final circuits | IUG: B/C 2x10 or 2x16 A depending on cross-section; TUG: C 2x16/2x20 A on 2.5 mm²; TUE: C 2x16 to 2x32 A depending on cross-section; PdCcc ≥ calculated Icc (with a 20 m line in 10 mm² it gives ≈ 3 kA: 4.5 kA) | Ib ≤ In ≤ Iz; circuit type | ELEC-PRO-1, -2, -3, -4 |

Before closing the single-line diagram: Icc at each panel (ELEC-PRO-3), I²t and maximum length of each circuit (ELEC-PRO-5), sum of PIAs
under each ID (ELEC-PRO-10), neutrals per ID (ELEC-PRO-25), selectivity main PIA / circuit PIAs, RCD S / 30 mA
and main switch / utility fuse (ELEC-PRO-12, -21, -29), and the DCI (installation conformity declaration) form if the job is in the
Edenor/Edesur area ([regulations-and-permits.md](regulations-and-permits.md)). If you want to review an existing panel or
a photo of a panel, use [reviewing-a-panel.md](reviewing-a-panel.md).

## What this guide does not replace
The design, calculation and signature of the installation are done by a professional or a qualified installer (*instalador habilitado*) according to the jurisdiction
(license (*matrícula*) category and scope set by each province or municipality). The utility decides on the service connection, the
metering, its fuses and the short-circuit data; the municipality, on the approval of the job. The AEA and IRAM tables
cited here are summaries: for design, use the current text of the regulations (AEA sells its editions) and the data
sheets from the manufacturer of each device. See [regulations-and-permits.md](regulations-and-permits.md).
