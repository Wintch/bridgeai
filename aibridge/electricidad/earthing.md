---
title: Earthing and system earthing arrangements
scope: protective earthing (*puesta a tierra*) in Argentine premises supplied at low voltage (dwellings, offices, shops, apartment buildings and site compounds); TT, TN-S, TN-C-S and IT systems; earth rod (*jabalina*), foundation earth electrode, inspection pit, earthing conductor, main earthing bar, protective conductor (PE), equipotential bonding; value of Ra, measurement (earth resistance tester (*telurímetro*), Wenner, loop, clamp) and the SRT 900/2015 protocol; how to lower a high earth resistance; socket outlets and plugs with earth; buildings, elevator, pumps, lightning protection, generator set, antennas; old installations without PE
when_to_use: designing or building the earth electrode of a job; choosing the cross-section of the PE or of the earthing conductor; an RCD (*ID*, *diferencial*) does not trip or trips on its own; measuring an earth or completing the annual protocol; the earth reads high; someone proposes "joining neutral to earth", an "isolated earth for the computer", an adapter or a Schuko; building with a transformer room, elevator, pumps, generator set or lightning protection; old house without an earth wire
related: [README.md, regulations-and-permits.md, grades-and-circuits.md, conductors-and-conduits.md, protection.md, panels.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md]
as_of: 2026-11-15
sources: [AEA 90364-7-771 Ed. 2006 (771.3, 771.5, 771.8.6.2, 771.18.3.5, 771.18.4, 771.18.5, 771.20.3.1, 771.23.5.2, Anexos 771-C and 771-D) and Corrigendum 1 (Jan 2007), AEA 90364-7-770 1st ed. 2017 (Ed. 2026 digital on sale, print on pre-order), AEA 90364-7-722 Ed. 2024 according to the AEA store (text consulted: 2nd expanded ed., dated 2023) (722.312, 722.543), Tienda AEA (AEA store) consulted 2026-11-15 (current editions of 90364, 92305 and AEA 95501/IRAM 2281), Res. SRT 900/2015 (BO 2015-04-28) with annex and instructions, Guía práctica SRT (SRT practical guide) for Res. 900/2015, Dec. 351/79 Anexo VI, Res. SIyC 16/2025 (BO 2025-02-25), Farina (Ingeniería Eléctrica 2021-2024), Arcioni (Ingeniería Eléctrica, Aug 2017), Facbsa and Tarea SRL (IRAM earth rod catalogs, Ingeniería Eléctrica 2015 and 2022)]
---
# Earthing and system earthing arrangements

How the earthing (*puesta a tierra*) of a low-voltage installation in Argentina is built, measured and maintained. Each rule has an
ID (`ELEC-PAT-n`) so the agent, a report or a message can cite it ("violates ELEC-PAT-2: neutral jumpered to earth at the
socket outlet (*toma*)"). Rules are never renumbered; a rule that is withdrawn is marked **Withdrawn** with the date and its replacement.

Calculator: `gateway electricidad earth --ra OHM --idn MA` checks Ra × IΔn ≤ 24 V, the 40 Ω maximum and the recommended
value from table 771.3.I; the phase cross-section comes from `gateway electricidad size`. As of 2026-11-15 the calculator
does **not** calculate the resistance of an earth rod (*jabalina*), of earth rods in parallel, or the resistivity by Wenner: for that the agent
uses the formulas in this guide and shows the calculation step by step, without rounding from memory.

**Safety first.** The earth is what protects you when everything else fails: while you are disconnecting or measuring it,
the installation is left without that protection. All work on the earth electrode, the earthing conductor or the bar is
done with **all** sources locked out (*consignadas*) (grid, generator set, UPS, inverters: ELEC-PAT-18; switched off, locked, verified
dead and tagged, see [site-safety.md](site-safety.md)). Never during a thunderstorm.
Never do live work. Before driving an earth rod or digging a trench, locate gas, sewer, water and buried cables.

## Current edition of the standards (as of 2026-11-15)
| Document | Edition | What we use it for here | Source |
|---|---|---|---|
| AEA 90364-7-771, Viviendas, oficinas y locales (unitarios) (dwellings, offices and single shops) | 2006 + Corrigendum 1 (Jan 2007) | Systems (771.3), deviations (771.5), earthing system (771.18.5), Anexos 771-C and 771-D | AEA store; text of Ed. 2006 |
| AEA 90364-7-770, Viviendas unifamiliares hasta 63 A (single-family houses) | 1st ed. 2017; Ed. 2026 digital on sale, print on pre-order | More didactic text of the same requirements (770.3, 770.14.4). Does not apply to an apartment building | AEA store; 2017 text |
| AEA 90364-7-772, Espacios comunes y servicios generales (common areas and common services) | 2019 | Common services of a building (elevator, pumps, landings) | AEA store |
| AEA 90364-7-701, Baños y locales con bañera o ducha (bathrooms and rooms with a bathtub or shower) | 2012 | Supplementary equipotential bonding in bathrooms | AEA store |
| AEA 90364-7-704, Obras de construcción y demolición (construction and demolition sites) | 2026 | Site compound installation | AEA store (text not consulted) |
| AEA 90364-7-710, Locales para uso médico (medical locations) | see AEA store | Operating rooms and medical locations (medical IT system) | Neither edition nor text consulted |
| AEA 90364-7-722, Alimentación de vehículos eléctricos (electric vehicle supply) | Ed. 2024 in the AEA store (2nd expanded ed.; the text consulted is dated 2023) | PE and system at charging points | AEA store; 2023 text |
| AEA 95501-1 / IRAM 2281-1, Puesta a tierra: conceptos y requisitos generales (earthing: concepts and general requirements) | 2026 | Basis of parts 2 and 3 | AEA store (text not consulted) |
| AEA 95501-2 / IRAM 2281-2, Guía de mediciones de magnitudes de puesta a tierra (guide to measuring earthing quantities) | 2021 | Measurement methods (fall of potential, Wenner) | AEA store (text not consulted) |
| AEA 95501-3 / IRAM 2281-3, Puesta a tierra de instalaciones ≤ 1 kV (earthing of low-voltage installations) | 2024 | Code of practice for LV earthing | AEA store (text not consulted) |
| IRAM 2309 (cylindrical copper-clad steel earth rod) and IRAM 2310 (cylindrical galvanized steel earth rod) | Current edition not confirmed (2309:2024 is mentioned) | Electrode | Titles per the bibliography of 771 Ed. 2006; text not consulted |
| AEA 92305-1 to -4 / IRAM 2184-1 to -4, Protección contra el rayo (lightning protection) | 2015 (part 11: 2016) | Lightning protection and its earthing | AEA store |
| Res. SRT 900/2015, Protocolo de medición de PAT y continuidad de masas (earthing and exposed-part continuity measurement protocol) | In force; no amendment found | Annual measurement in workplaces | Boletín Oficial 2015-04-28; instructions read on argentina.gob.ar |

> A 4-story apartment building falls under 771 (units) and 772 (common areas). Where we cite 770 it is
> because its text explains the same thing as 771 more clearly. AEA and IRAM standards are paid: here they are summarized and
> cited, not transcribed.

## Quick reference
| Situation | Rule |
|---|---|
| Which system do I use? Can I do TN-S? | ELEC-PAT-1 |
| "I joined neutral to earth and it works" / socket outlet with an N-PE jumper | ELEC-PAT-2 |
| The utility (*distribuidora*) asks for an earth rod at the meter pillar (*pilar*) | ELEC-PAT-2, ELEC-PAT-3 |
| Where to drive the earth rod, which earth rod to buy, what it will read | ELEC-PAT-3, ELEC-PAT-4 |
| Inspection pit, earth rod clamp (*tomacable*), test link | ELEC-PAT-5 |
| Cross-section of the cable from the earth rod to the panel (*tablero*) | ELEC-PAT-6 |
| Cross-section and route of the PE | ELEC-PAT-7 |
| Water/gas pipes, structure, bathrooms | ELEC-PAT-8 |
| How many ohms must it read? | ELEC-PAT-9 |
| How to measure with an earth resistance tester (and if there is no room on the lot) | ELEC-PAT-10 |
| Measuring with a clamp, selective method or loop tester | ELEC-PAT-11 |
| Shop, office, factory or construction site: annual protocol | ELEC-PAT-12 |
| The earth reads high | ELEC-PAT-13 |
| Socket outlets, plugs, adapters, Schuko, "biuso" (dual-standard outlet) | ELEC-PAT-14 |
| Building: main bar, riser, transformer room | ELEC-PAT-15 |
| Elevator, pumps, tanks, metal structures | ELEC-PAT-16 |
| Lightning protection | ELEC-PAT-17 |
| Working on the earth without risk | ELEC-PAT-18 |
| Maintenance and periodic inspection | ELEC-PAT-19 |
| Site compound and site panel | ELEC-PAT-20 |
| Generator set | ELEC-PAT-21 |
| "Isolated earth" or "computer earth" (*tierra aislada*, *de informática*) | ELEC-PAT-22 |
| Old house or building without an earth wire | ELEC-PAT-23 |
| New build: electrode in the foundations | ELEC-PAT-24 |
| Measuring soil resistivity (Wenner) | ELEC-PAT-25 |
| Antennas, coaxial, door entry system (*portero*), AC outdoor units | ELEC-PAT-26 |
| Photovoltaics, EV charger, pool, electric shower | ELEC-PAT-27 |
| Voltage between neutral and earth, "kick" (*patada*), RCD that trips when it rains | ELEC-PAT-28 |

### Key values
| Quantity | Value | Source |
|---|---|---|
| Safety voltage / conventional touch voltage limit (UL) in dry and damp locations | 24 V AC to earth | Dec. 351/79, Anexo VI, item 1 (definition of "tensión de seguridad"); AEA adopts it as UL (table 771.3.I, col. 2 "para UL 24 V") |
| Maximum Ra of the protective earth in TT with an RCD of IΔn ≤ 300 mA | 40 Ω (permanent maximum value) | AEA 771 Ed. 2006, 771.3.3.1, 771.18.5.2 and table 771.3.I col. 3 (it used to be 10 Ω) |
| Maximum Ra with a 500 mA / 1 A RCD | 24 Ω / 12 Ω | Table 771.3.I col. 3 (= half of 24 V / IΔn) |
| Theoretical Ra for UL = 24 V with a 30 mA / 300 mA RCD | 800 Ω / 80 Ω (= 24 V / IΔn) | Table 771.3.I col. 2 |
| Maximum disconnection time in TT, final circuits at 230 V / sub-main circuits | 0.2 s / 1 s | AEA 771, table 771.18.I and its note 1 |
| Rb (neutral system earth) in TN-S with own transformer | ≤ 2 Ω (better ≤ 1 Ω) | SRT guide Res. 900/2015 |
| Earth of a generator set's neutral | ≤ 10 Ω, separate from that of the public grid | AEA 771, 771-D.8.2 |
| Lightning protection earth (recommended, not required) | ≤ 10 Ω measured with a low-frequency earth resistance tester | SRT guide Res. 900/2015 citing IEC 62305 / AEA 92305 |
| Separation protective earth ↔ system earth | > 10 equivalent radii (≈ 3.2 m for a 1/2" or 5/8" × 1.5 m earth rod; ≈ 5.6 m for 5/8" × 3 m) | AEA 771, 771.3 note 3, 771.18.5.3 and table 771.3.II |
| Minimum earth rod | copper-clad steel IRAM 2309: JL14 × 1500 mm (12.6 mm); galvanized steel IRAM 2310: JL16 × 1500 mm | AEA 771, 771-C.2.2.1 |
| Recommended spacing between earth rods in parallel | ≥ 2 times the length of the longest one | AEA 771, 771-C.2.2.4 note 2 |
| PE: absolute minimum cross-section | 2.5 mm² Cu | AEA 771, 771.18.5.6 and 771.18.5.7 |
| Earthing conductor: absolute minimum cross-section | 4 mm² Cu | AEA 771, 771.18.5.5 (table 771.18.III) |
| Validity of the earthing (PAT) protocol in workplaces | 12 months | Res. SRT 900/2015, art. 2 |
| PE continuity instrument | ≥ 200 mA, 4 to 24 V open-circuit (IEC 61557-4) | SRT guide Res. 900/2015 |

## Concepts: the systems in two lines
The first letter says how the source is related to earth; the second, how the exposed conductive parts of the installation are.

| System | Source | Exposed parts | In Argentina | Protection against indirect contact |
|---|---|---|---|---|
| **TT** | Neutral to earth at the utility's transformer (system earth, Rb) | To the premises' own earth (protective earth, Ra), separate from Rb | **Mandatory** in all premises supplied at LV from the public grid (771.3.2, 771.18.5.1) | RCD only (the fault current is small, the MCB (*térmica*) does not trip) |
| **TN-S** | Neutral to earth | Connected to the source neutral by a PE separate from N along the whole route | Only with MV/HV supply (own transformer), with own generator, or on the secondary of an LV/LV transformer (771.3.2 notes 2 and 3) | MCB/fuse if the disconnection time is verified; 30 mA RCD on final circuits anyway |
| **TN-C** | Neutral to earth | Connected to a single PEN conductor (neutral and earth together) | **Prohibited** in building installations (exception: section between the LV terminals of the own transformer and the main switch) | — |
| **TN-C-S** | Neutral to earth | PEN up to a point, then N and PE separate | **Prohibited** in internal building installations, except for the exception in AEA 90364-3, 312.2.1.1 | — |
| **IT** | Isolated from earth (or through high impedance) | To own earth | Special cases (processes that cannot be interrupted; medical locations per AEA 90364-7-710); requires an insulation monitor | See 771.3.3.3 and 771-H.5 (cited in table 771.18.I) |

Source: AEA 771 Ed. 2006, 771.3.2 and 771.3.3; Guía práctica SRT Res. 900/2015; Farina, "Conexión a tierra de las
instalaciones" (earthing of installations), Ingeniería Eléctrica (2021); AEA 90364-3, 312.2.

## Rules

### ELEC-PAT-1: Utility supply at low voltage = TT system, no option
- **Rule:** all premises that receive energy at low voltage from the public grid (the utility's meter is at LV) are built as a TT system: the premises' own protective earth, independent of the utility's neutral earth, and RCD protection. Another system (TN-S or IT) is only possible if energy is bought at medium voltage, if the source is an own generator, or on the secondary of an LV/LV transformer. TN-C and TN-C-S are prohibited inside the premises.
- **Why:** in TT the fault current to an exposed part flows through both earths (Ra + Rb) and is low; the MCB does not trip and the exposed part stays at a dangerous voltage. That is why in TT the only accepted protection against indirect contact by automatic disconnection is the RCD, coordinated with a limited Ra.
- **How:**
  1. Confirm with the utility at what voltage it supplies. If it supplies at LV (the case of almost every dwelling and apartment building), it is TT.
  2. If the establishment needs TN-S or IT for a process, an LV/LV (isolating) transformer is installed and the desired system is adopted on its secondary.
  3. Record the system in the job documentation and in the protocol (item 26 of the instructions of Res. SRT 900/2015).

  *Worked example (why the MCB is not enough in TT):* phase-to-exposed-part fault in an appliance, U0 = 220 V, Rb = 1 Ω, Ra = 10 Ω, cables and transformer neglected. Id = U0 / (Ra + Rb) = 220 V / 11 Ω = 20 A. A 20 A C curve MCB needs between 5 and 10 × In (100 to 200 A) to trip instantaneously: it does not trip. The exposed part stays at Id × Ra = 20 A × 10 Ω = 200 V. With Ra = 40 Ω: Id = 220 / 41 ≈ 5.4 A and the exposed part stays at ≈ 215 V. Only the RCD disconnects.
- **Verify:** that every circuit and every line has protection against indirect contact (RCD, or double insulation on the main line and on the lines without an RCD: ELEC-PAT-15); 30 mA RCD on all final circuits (ELEC-PAT-9); that in the main panel there is no jumper between the neutral bar and the earth bar; that the protective earth is separate from the system earth (ELEC-PAT-3).
- **Don't:** "make it TN" by joining the PE to the service drop (*acometida*) neutral because the earth rod read high; rely on the MCB to protect people in a TT system.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.3.2 (TT required with public LV; notes 2 and 3: MV/HV, own generator or LV/LV transformer), 771.18.5.1 and 771.18.4.3 (in TT only RCDs; its note 2 does the same calculation with a 16 A PIA); Guía práctica SRT Res. 900/2015 (TN-C prohibited; TN-C-S prohibited in internal installations except AEA 90364-3, 312.2.1.1; example Id = 20 A); AEA 770.14.3.2 (1st ed. 2017).

### ELEC-PAT-2: The neutral is never the earth
- **Rule:** the neutral (N, light blue) and the protective conductor (PE, green-yellow) are separate conductors from the main panel to the last socket outlet. In TT they are never joined together at any point of the user's installation: not at the socket outlet, not in the box, not in the panel.
- **Why:** if the neutral acts as earth, an unbalanced load or a broken neutral puts voltage on all the exposed parts of the installation at the same time; in addition the RCD is defeated or trips for no reason, because part of the return current flows through the PE.
- **How:**
  1. In the panel: insulated neutral bar and separate earth (PE) bar, both identified (see [panels.md](panels.md), ELEC-TAB-15).
  2. At each socket outlet: phase and neutral on their terminals, PE only to the earth terminal.
  3. The "puesta a tierra de servicio suplementaria" (supplementary system earth) that some utilities require at the meter pillar, joined to the service drop neutral, is a reinforcement of the grid's system earth: it is not your protective earth and must be more than 10 equivalent radii away from it (ELEC-PAT-3).
- **Verify:** dead, with the double-pole main switch of the main panel open (it also cuts the grid neutral), all appliances unplugged and the SPD (*DPS*) disconnected, measure with a megohmmeter (*megóhmetro*) at 500 V DC between the neutral bar and the PE bar: it must give an insulation value (megohms; minimum per [testing-and-commissioning.md](testing-and-commissioning.md), ELEC-MED-4), not a few ohms. If the main switch does not cut the neutral, the installation is already wrong (ELEC-TAB-9). Never touch the service drop neutral or the meter terminals to do this test. Typical symptom of an N-PE jumper downstream of an RCD: the RCD trips when loads are connected or cannot be reset (see [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Don't:** jumper neutral and earth at the socket outlet "so the appliance has earth"; use the service drop or utility neutral as PE; connect the PE to the neutral terminal of the meter or the meter pillar; measure N-PE with the grid neutral connected (the ohmmeter sees the loop N → Rb → earth → Ra → PE, tens of ohms, and it looks like "continuity").
- **Source:** AEA 771 Ed. 2006, 771.3 note 6 (utility's supplementary system earth, independent and more than 10 equivalent radii from the protective earth) and figure 771.3.A; Guía práctica SRT Res. 900/2015 (Ra "no debe vincularse con la tierra de servicio Rb" (must not be linked to the system earth Rb)); AEA 90364-3, 312.2.1.1. Insulation test: AEA 771, 771.23 (table 23.I).
### ELEC-PAT-3: The protective earth goes far from the system earth and inside the premises
- **Rule:** the protective earth electrode is located within the boundaries of the premises and more than 10 equivalent radii from the nearest system earth electrode of the utility (neutral earth rod (*jabalina*) at the meter pillar (*pilar*), in the transformer room or on the grid), measured in any direction, taking the radius of the longest earth rod.
- **Why:** if the two earths are close, they influence each other: a fault on the grid raises the potential of your earth and the system stops being TT in practice (it starts behaving like TN-S without meeting its conditions).
- **How:** for a cylindrical earth rod, 771 gives the approximate equivalent radius as **Re ≈ L / ln(L/d)** (L length and d diameter, in m) and tabulates it in table 771.3.II. It is a different formula from the resistance formula in ELEC-PAT-4: don't derive the radius from that other one. Values of 10 Re per the table: earth rod of 1/2" or 5/8" × 1.5 m ≈ 3.2 m; 5/8" × 3 m ≈ 5.6 m; 3/4" × 6 m ≈ 10.2 m. If the electrode is a mesh, tape or plate, the radius is calculated for that arrangement. If the separation cannot be achieved within the lot, 771.5.1 requires asking the utility (*distribuidora*) for cooperation (see ELEC-PAT-15).

  *Worked example:* earth rod 5/8" × 3 m: L/d = 3 / 0.0146 = 205.5; ln(205.5) = 5.33; Re = 3 / 5.33 = 0.563 m; 10 Re = 5.6 m (matches table 771.3.II).
- **Verify:** distance measured on site between the protective earth rod and any utility earth rod, recorded on the sketch (*croquis*).
- **Don't:** drive the protective earth rod next to the meter pillar "because it's convenient"; place it on the neighbor's land or on the sidewalk.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.3 notes 3 to 6 (independent earth, IEV 195-02-02; 10 equivalent radii of the longest earth rod; expression for Re), table 771.3.II, 771.18.5.3 and 771.5.1; Corrigendum 1 (Jan 2007, figure 771.5.A); AEA 770, 770.3 (table 770.3.I, 1st ed. 2017).

### ELEC-PAT-4: Electrode: IRAM standard earth rod (*jabalina*), buried joints welded or compressed
- **Rule:** electrodes (earth rods, tapes, plates, cables) comply with the corresponding IRAM standard. The usual one is the cylindrical copper-clad steel earth rod IRAM 2309; there is also the galvanized steel one, IRAM 2310. The minimum earth rod allowed is JL14 × 1500 mm (12.6 mm, copper-clad steel) or JL16 × 1500 mm (galvanized steel). Buried joints between electrodes are made with exothermic welding (*soldadura cuproaluminotérmica*) or, between parts of equal cross-section, by oval or hexagonal compression.
- **Why:** the earth electrode is buried and cannot be seen: a material that corrodes or a loose joint raises the resistance without warning. The copper layer bonded to the steel core resists soil corrosion and the steel gives the stiffness to drive it.
- **How:**
  - Commercial sizes of IRAM 2309 earth rods: diameters 12.6 mm (1/2", designation JL14), 14.6 mm (5/8", JL16) and 16.2 mm (3/4", JL18); the JL number is a commercial designation, not the exact diameter in mm. Lengths 1.5 m, 2 m and 3 m (plain) and couplable sections with a bronze coupling sleeve (*manguito*) and driving head (*sufridera*) for deep driving.
  - The most used in dwellings is 5/8" × 1.5 m; in buildings it is common to go to 3 m or to couplable earth rods depending on soil resistivity (ELEC-PAT-13, ELEC-PAT-25).
  - An IRAM earth rod has the brand, model, year and standard engraved on it: if nothing is engraved, it is not IRAM.
  - **Danger, before driving or trenching:** locate buried services (drawings, gas route from the meter, the utility's underground service connection, sewer, water). If in doubt, probe the first 0.5 to 0.8 m with a shovel. Never drive on the line between the gas meter and the house or next to the underground service connection (see [site-safety.md](site-safety.md), ELEC-SEG-19).
  - It is driven by hammering (with a driving head on couplable rods), without drilling if the ground allows it; the head ends up inside the inspection pit (ELEC-PAT-5).

  *Worked example (resistance of one earth rod, 771-C.10.1):* R = [ρ / (2π L)] × [ln(8L/d) − 1]. With ρ = 100 Ω·m (typical clay soil), L = 1.5 m, d = 0.0146 m (5/8"): ρ / (2π L) = 100 / 9.425 = 10.61 Ω; 8L/d = 12 / 0.0146 = 821.9; ln(821.9) = 6.712; 6.712 − 1 = 5.712; R = 10.61 × 5.712 ≈ **61 Ω** (does not meet 40 Ω). With L = 3 m: 5.305 × (7.405 − 1) ≈ **34 Ω** (meets it, with little margin). With ρ = 50 Ω·m and 5/8" × 1.5 m: ≈ 30 Ω. Doubling the length lowers it much more than doubling the diameter. Quick check with the simplified form from the same clause: for L/d between 100 and 600, R ≈ ρ/L = 100/1.5 ≈ 67 Ω (same order).

  > Careful with the formula: Farina (Ingeniería Eléctrica, Jun 2023) transcribes it as ln(8L/d − 1), with the −1 inside the logarithm, and his table (ρ = 50 Ω·m) gives 15-17 % more; with that version the first case would give ≈ 71 Ω. The simplified forms that 771-C.10.1 itself gives (≈ 0.75 ρ/L, ≈ ρ/L and ≈ 1.2 ρ/L depending on L/d) only work out with the −1 outside, which is also Dwight's classic formula (IEEE Std 142). Use this one. In any case it is an estimate: the value that counts is the measured one (ELEC-PAT-10).
- **Verify:** IRAM engraving on the earth rod and on the earth rod clamp (*tomacable*); buried joints welded or compressed, never bolted underground; sketch with the location of gas, sewer and service connection before driving.
- **Don't:** use water pipes, loose rebar or steel sections as an "earth rod"; splice underground with terminals or tape; use earth rods shorter than 1.5 m or with a diameter below the minimum; drive without knowing what is underneath.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.18.5.2 (IRAM electrodes; exothermic joints or oval or hexagonal compression), 771-C.2.2.1 (list of electrodes and minimum sizes: JL14 × 1500 copper-clad steel IRAM 2309, JL16 × 1500 galvanized steel IRAM 2310) and 771-C.10.1 (formula and simplified forms); bibliography of 771 (titles of IRAM 2309 and 2310); designations JL14/JL16/JL18: Facbsa (Ingeniería Eléctrica, Oct 2015) and Tarea SRL (Ingeniería Eléctrica, Aug 2022); Farina, "Sistema de puesta a tierra. Parte 7" (earthing system, part 7), Ingeniería Eléctrica, Jun 2023 (table for ρ = 50 Ω·m). **Not verified in a primary source:** minimum copper thickness of IRAM 2309 (manufacturers state 250 to 254 µm); the exact reading of formula 771-C.10.1 was deduced from its text and its simplified forms because the available copy has the equation illegible.

### ELEC-PAT-5: Inspection pit with a cover and a disconnection point for measuring
- **Rule:** the joint between the earth electrode (bare) and the earthing cable (insulated) is made inside an inspection pit with a removable cover at finished floor level, preferably in a place that is not permanently walked or driven on and is free of obstacles. The connection allows the electrode to be disconnected to measure it: an electrolytic copper bar with removable links or, if the electrode is a single IRAM 2309 earth rod, a bronze or brass earth rod clamp (*tomacable*).
- **Why:** the earth is measured with the electrode disconnected from the installation (ELEC-PAT-10); without a pit or a link, every measurement means breaking something or it is measured wrong. The pit also lets you see corrosion.
- **How:** cast iron, concrete or synthetic pit suitable for burying (manufacturers offer square boxes of 150 mm and 250 mm per side); if it is in a garage, a cast iron cover rated for vehicle traffic and out of the wheel tracks; earth rod clamp of the earth rod's diameter, well tightened; insulated green-yellow cable going to the panel (*tablero*) in conduit. If there are several earth rods, all of them end in pits and the interconnection is made there.
- **Verify:** cover accessible, inside dry and clean, earth rod clamp tight and free of verdigris or rust, "PAT" marking.
- **Don't:** cover the pit with floor screed (*contrapiso*) or tiles; bury the connection without a pit; join the cable to the earth rod with twisted wire.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.18.5.4 "Cámara de inspección" (inspection pit) and 771-C.2.2.4 note 2 (connection of multiple electrodes in pits); AEA 770, 770.14.4.3 (1st ed. 2017); box sizes: Tarea SRL (2022). **Not verified in a primary source:** the IRAM standard numbers for the earth rod clamp (IRAM 2343 is cited) and for compression joints (IRAM 2349 is cited): 771 does not mention them.

### ELEC-PAT-6: Earthing conductor: minimum 4 mm², insulated, to the main panel
- **Rule:** the cable that connects the earth electrode to the main equipotential bonding bar (or to the main earthing bar) is sized with the same table as the PE (table 771.18.III, see ELEC-PAT-7) and is never smaller than 4 mm² copper. It is run independently of the circuit PEs (even if they share the conduit) and enters through the main panel.
- **Why:** it is the only path between all the exposed parts and earth; it must carry the fault current without overheating and it is the most exposed section (buried, outdoors). Entering through the main panel helps overvoltage protection.
- **How:** green-yellow insulated copper inside conduit from the pit to the main panel, with no splices. If it cannot enter through the main panel, entering through the box or panel closest to the electrode is allowed; in that case, from there a conductor of equal cross-section continues, without interruptions, to the main bar, which remains the single point of connection. Finish with a lug on the bar.
- **Verify:** cross-section ≥ 4 mm² and ≥ the one the table gives for the phase cross-section of the main line; continuity between the earth rod clamp and the bar.
- **Don't:** use a circuit's PE as the earthing conductor; splice it inside a junction box; terminate it in a sub-panel (*tablero seccional*) as if it were the main bar; leave it bare and unprotected on a wall.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.18.5.5 (entry through the main panel or, if not possible, through the nearest box or panel; table 771.18.III; minimum 4 mm²; run independently of the PE and connected to the main equipotential bonding bar); AEA 770, 770.14.4.4 (1st ed. 2017).

### ELEC-PAT-7: The PE runs through the whole installation, unbroken and with the table cross-section
- **Rule:** an insulated green-yellow copper protective conductor runs through the whole installation from the main earthing bar, through every box and outlet point (*boca*) (including those without a socket outlet (*toma*)), with this minimum cross-section according to the phase cross-section S of the circuit or line it accompanies:

  | Phase cross-section S | Minimum cross-section of the PE (and of the earthing conductor) |
  |---|---|
  | S ≤ 16 mm² | Equal to S |
  | 16 mm² < S ≤ 35 mm² | 16 mm² |
  | S > 35 mm² | S / 2 |
  | In no case | PE ≥ 2.5 mm² (earthing conductor ≥ 4 mm²) |

  If the PE is not mechanically protected, 4 mm² minimum; in trays or trunking it may be bare under the conditions of the standard. If the phase cross-section was increased only because of voltage drop, the PE may be smaller than the phase as long as it meets its thermal and short-circuit calculation (in the technical report, *memoria técnica*).
- **Why:** the PE carries the fault current until the RCD (*diferencial*) disconnects; if it is broken or too thin, the exposed part stays energized or the conductor burns. The green-yellow color is exclusive so no one uses it as phase or neutral.
- **How:**
  1. Branch off without cutting the through conductor: from the PE line that runs along the conduit, green-yellow branches of 2.5 mm² minimum go to the terminal of each socket outlet, metal box, metal conduit, panel or appliance.
  2. It is only interrupted for changes of cross-section at sub-panels and in properly made splices.
  3. Earth terminals marked with the protective earth symbol, the letters PE or green-yellow; the marking does not go on a screw that comes out.
  4. Continuity between metal box and metal conduit with fittings that do not loosen. In metal panels, door and inner cover (dead front, *contratapa*) bonded to the PE with a braid or cable (see [panels.md](panels.md), ELEC-TAB-5); metal trays with continuity between sections.

  *Worked example:* sub-main of an apartment (*depto*) in 10 mm² → PE 10 mm². Common services riser (*montante*) in 25 mm² → PE 16 mm². Feeder in 50 mm² → PE 25 mm². Socket outlet circuit in 2.5 mm² → PE 2.5 mm².
- **Verify:** continuity of each PE with an instrument per IEC 61557-4 (≥ 200 mA, 4 to 24 V open-circuit) from the bar to each earth terminal (see [testing-and-commissioning.md](testing-and-commissioning.md), ELEC-MED-3).
- **Don't:** connect exposed parts "daisy-chained" (*en guirnalda*: in series, from one to the next, cutting the PE); use green-yellow for anything else; leave metal boxes or class I appliances without PE; replace the PE with the metal conduit.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.18.5.6 (insulated PE IRAM NM 247-3/2178/62266/62267 throughout the installation; minimum 2.5 mm²; smaller PE due to voltage drop with calculation; no interruptions except changes of cross-section and splices; note 2: daisy-chaining prohibited) and 771.18.5.7 (identified terminals, box-conduit continuity, branches ≥ 2.5 mm²), table 771.18.III; Guía práctica SRT Res. 900/2015, item 30 (2.5 mm² protected / 4 mm² unprotected, AEA 90364-5 table 54.5). Phase cross-sections: [conductors-and-conduits.md](conductors-and-conduits.md).

### ELEC-PAT-8: All extraneous conductive parts to the equipotential bar; nothing metallic acts as an electrode
- **Rule:** metal parts that are not part of the electrical installation but can carry a potential (extraneous conductive parts: water, gas, heating and air conditioning pipes, reinforcement and metal structure, cable trays, metal columns) are connected with bonding conductors to the main equipotential bonding bar (or to the earth bar of the main panel if there is none). In bathrooms with a bathtub or shower, the supplementary equipotential bonding required by AEA 90364-7-701 is also done. No pipe is used as an earth electrode or as PE.
- **Why:** in a fault, the danger is the potential difference between two things you touch at the same time (the tap and the refrigerator). If everything is bonded to the same earth, that difference stays small. Pipes are no good as an electrode: they can be replaced with plastic, have insulating joints or carry gas.
- **How:**
  1. Copper main equipotential bonding bar next to the main panel (in buildings, in the meter room or main panel: ELEC-PAT-15), with the earthing conductor connected to it.
  2. Green-yellow bonding conductors from the bar to each extraneous conductive part, with an earthing clamp suitable for the pipe, at the point of entry into the premises.
  3. Gas piping: bond it on the inside of the premises, downstream of the meter and of the dielectric joint if there is one; coordinate with the licensed gas fitter (*gasista matriculado*) whatever the gas utility requires.
  4. In bathrooms: bond accessible metal parts (metal pipes, metal bathtub, grates) to each other and to the PE per 701 (see [special-installations.md](special-installations.md), ELEC-ESP-5).
- **Verify:** continuity between each extraneous conductive part and the equipotential bar; in workplaces it is reported in the SRT protocol (item 29: earthing circuit "continuo y permanente" (continuous and permanent); see ELEC-PAT-12).
- **Don't:** use the water or gas piping as "earth"; leave the metal structure of a shop or a shed (*tinglado*) unbonded; bond the gas without consulting whoever is responsible for that installation.
- **Source:** AEA 90364-7-771 Ed. 2006, 771-C.2.2.4 note 1 (pipes for water, flammable liquids or gases, heating and cable sheaths are not used as electrodes but are always bonded to the main equipotential bonding bar) and Anexo 771-C.8; Guía práctica SRT Res. 900/2015 (extraneous conductive parts to be listed); instructions of Res. SRT 900/2015, item 29; AEA 90364-7-701 (Ed. 2012). **Not verified in a primary source:** the details of the supplementary equipotential bonding in 701 (cross-sections and which parts) and the gas utility's requirement on the bonding point.
### ELEC-PAT-9: Ra coordinated with the RCD (*diferencial*): Ra × IΔn ≤ 24 V and, in practice, Ra ≤ 40 Ω
- **Rule:** in TT, the resistance of the protective earth Ra must meet Ra × IΔn ≤ UL (24 V), with IΔn the residual operating current of the protecting device. Since the ground varies with the seasons, AEA sets as the permanent maximum the values in column 3 of table 771.3.I: **40 Ω when the RCD (*disyuntor* / *diferencial*) has IΔn ≤ 300 mA**, and lower values with low-sensitivity RCDs (24 Ω with 500 mA, 12 Ω with 1 A). In addition, **all** final circuits (IUG, IUE, TUG, TUE and the specific-use ones) have an instantaneous RCD (ID) with IΔn ≤ 30 mA as additional protection against direct contact, with no limit on the circuit current.
- **Why:** in a fault, the exposed part sits at Id × Ra. If Ra meets the condition, the RCD disconnects before that voltage becomes dangerous. With a 30 mA RCD the theoretical limit is huge (800 Ω), but AEA does not accept more than 40 Ω, to keep a margin and so that the incoming 300 mA RCDs work.
- **How:**

  | RCD IΔn | Theoretical Ra for 24 V (= 24 V / IΔn) | Maximum allowed Ra (table 771.3.I, col. 3) |
  |---|---|---|
  | 30 mA | 800 Ω | 40 Ω |
  | 300 mA | 80 Ω | 40 Ω |
  | 500 mA | 48 Ω | 24 Ω |
  | 1 A | 24 Ω | 12 Ω |

  Column 3 is half of 24 V / IΔn, capped at 40 Ω; it is the criterion used by `gateway electricidad earth`.

  *Worked example:* building with a 300 mA selective RCD on the common services line and 30 mA RCDs on the circuits. Measured Ra = 28 Ω. Touch voltage with the incoming RCD at its tripping limit: 28 Ω × 0.3 A = 8.4 V ≤ 24 V, and 28 Ω ≤ 40 Ω: it complies. If the measurement gave 55 Ω, the theoretical calculation would also work out (55 × 0.3 = 16.5 V) but it does not meet AEA's 40 Ω maximum: the earth must be improved (ELEC-PAT-13).
- **Verify:** measured value (ELEC-PAT-10) ≤ 40 Ω or the table value for the installed RCD; date and ground condition recorded. Good practice (not a requirement): if you measure with damp soil or after rain, don't accept a borderline value; aim for about 20 Ω (half the maximum) or measure again with dry soil, because 771 requires that soil drying does not take the resistance above the allowed value.
- **Don't:** accept more than 40 Ω "because it has a 30 mA RCD anyway"; fit an incoming RCD of 500 mA or more without recalculating Ra; use the 10 Ω value from the 2002 edition as if it were the requirement today (it is good practice, not the requirement); leave the AC, oven or pump circuit outside the 30 mA RCD "because it's over 32 A" (in dwellings there is no such exception).
- **Source:** AEA 90364-7-771 Ed. 2006, 771.3.3.1, 771.18.5.2 and table 771.3.I (its note 2 matches it to table 53 C of 531.2.4.2.2 of AEA 90364-5; the foreword says the maximum went from 10 to 40 Ω), 771.18.3.5 (instantaneous RCD ≤ 30 mA on all the listed final circuits; only exception: single-load circuit with proven disturbance, with conditions) and 771-C.2.2.2 (soil drying); Guía práctica SRT Res. 900/2015 (40 Ω with IΔn ≤ 300 mA; UL = 24 V per Dec. 351/79). The "up to 32 A" that appears in the SRT guide and in IEC 60364-4-41 (411.3.3) is a general minimum, not the scope of 771. Choosing RCDs: [protection.md](protection.md) (ELEC-PRO-7).

### ELEC-PAT-10: Measure with an earth resistance tester (*telurímetro*) by fall of potential, with the electrode disconnected, and record it
- **Rule:** the resistance of the earth electrode is preferably measured with an earth resistance tester (IEC 61557-5) by the fall-of-potential method, with the electrode disconnected from the installation (link open in the pit), and it is recorded with date, instrument, method, distances, ground condition and sketch.
- **Why:** with the electrode connected you measure in parallel with other earths (pipes, the neighbor's through the neutral) and the number comes out optimistic. The fall-of-potential method done properly gives the real value of the electrode.
- **How:**
  1. All sources locked out (ELEC-PAT-18). Open the link or release the earth rod clamp (*tomacable*) in the pit. If not everything can be locked out, don't open the earth: use the selective method or the loop (ELEC-PAT-11).
  2. Drive in a straight line, moving away from earth rod (*jabalina*) X: the current stake (*pica*) C at a distance D that is large compared with the size of the electrode (for a 1.5 to 3 m earth rod, 20 to 50 m is usual), and the potential stake P at 62 % of D from X.
  3. Measure with P at 62 % and repeat with P at 52 % and at 72 % of D (± 10 % of D). Example: D = 30 m → P at 15.6 m, 18.6 m and 21.6 m. If the three readings are within ± 5 % of their average, the value is valid; if not, move C farther away and repeat.
  4. Stakes and leads away from buried pipes and other earth rods; with dry soil, wet the auxiliary stakes (not the earth rod being measured).
  5. **No room on the lot** (lot between party walls): run the leads along a passage, the sidewalk (with permission) or in another clear direction; on concrete or tiles use metal plates or mats laid flat and wetted (an earth tester accessory) as auxiliary electrodes instead of stakes. If even so the distance cannot be achieved, don't record a measurement with stakes at 5 m: report the loop measurement as an upper bound (ELEC-PAT-11) and record the method.
  6. Reconnect the electrode, tighten the earth rod clamp and record that it was left connected.

  *Why 62 %:* for point electrodes in homogeneous soil, the error cancels out when XP / XC = (√5 − 1) / 2 ≈ 0.618.

  *Alternative in 771 (voltmeter-ammeter):* variable resistor of 20 to 100 Ω, ammeter, voltmeter of more than 40 kΩ and a probe buried at 0.5 m and at 20 m or more from the electrode; R = V / I. First, with the circuit open, the voltmeter must read zero or almost zero; if not, there are stray currents and the method is no good. It is a measurement with mains voltage: trained personnel only.
- **Verify:** schedule (*planilla*) with value, method, distances used, instrument and calibration date, ground condition (dry, damp, recent rain), electrode number matching the sketch.
- **Don't:** measure with a multimeter between phase and earth rod or with a test lamp (it is dangerous and does not measure Ra); drive the stakes 2 or 3 m from the earth rod; measure with the electrode connected and record the value as if it were Ra.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.23.5.2 (earth resistance tester preferred; voltmeter-ammeter method as alternative) and 771-C.2.2.1 (verify the resistance by measurement at the end of the job); Arcioni, "Mediciones telurimétricas de las resistencias de las puestas a tierra" (earth resistance measurements), Ingeniería Eléctrica, Aug 2017 (derivation of the 62 %; cites IRAM 2281-2:2002, clause 6.2.4, and the ± 5 % criterion and C at 30-50 m from BS 7430:1991, 16.2.2); AEA 95501-2 / IRAM 2281-2 Ed. 2021 (current edition per the AEA store; its text was not consulted, clause 6.2.4 may have another number). Contact plates for hard surfaces: standard earth tester accessory (manufacturers' catalogs). Full test procedure: [testing-and-commissioning.md](testing-and-commissioning.md) (ELEC-MED-5).

### ELEC-PAT-11: Earth clamp, selective method and loop tester: useful in some cases, they don't replace the earth resistance tester
- **Rule:** the clamp method (stakeless) only measures correctly when the electrode is part of a system with several electrodes in parallel that provide a low-resistance return path; in a TT dwelling or building with a single electrode it does not apply. The selective method (earth resistance tester with stakes + clamp) measures one electrode without disconnecting it. Measuring the fault loop impedance (phase-PE) is an accepted option to put an upper bound on Ra in TT.
- **Why:** the clamp induces a voltage in the loop and measures the current that flows; if there is no other electrode to close the loop through, there is no useful loop. The loop tester measures Ra + Rb + cables: it gives a value higher than Ra, so if that value already complies, Ra complies.
- **How:**
  - Selective: stakes C and P as in ELEC-PAT-10, and the tester's clamp around only that earth rod's conductor; the instrument subtracts the current that goes through other paths. Useful when the building cannot be locked out to open the earth.
  - Loop: with a loop tester (IEC 61557-3) at a protected socket outlet (*toma*), always **phase-PE** (not phase-neutral). Use the no-trip mode (test current of about 15 mA or less): in high-current mode the 30 mA RCD trips. During the test the exposed parts rise in potential: no one should touch metal parts. If it measures, for example, 18 Ω, report "Ra < 18 Ω" and it meets 40 Ω. It is a live measurement: trained personnel do it (see [testing-and-commissioning.md](testing-and-commissioning.md), ELEC-MED-9).
  - Clamp alone: useful on networks with many interconnected earths (poles, mesh systems with several down conductors) and to detect leakage currents (*corrientes de fuga*) flowing in the earth conductor.
- **Verify:** that the report states which method was used and, if it was the loop, that it is reported as an upper bound ("less than").
- **Don't:** measure a single dwelling earth rod with the clamp alone and record the number; report the loop value as if it were the exact Ra; use the loop tester's high-current mode downstream of a 30 mA RCD.
- **Source:** Guía práctica SRT Res. 900/2015 (three options from the RAEA: earth resistance tester, voltmeter-ammeter method, fault circuit impedance, reporting "Ra < valor" (Ra < value)); Fluke, "Cuatro métodos para realizar pruebas de puesta a tierra" (four methods for earth testing) (clamp with earths in parallel; selective method). **Not verified in a primary source:** that AEA or IRAM 2281-2 expressly exclude the clamp on a single electrode (it is deduced from the measuring principle); the no-trip mode current varies by manufacturer.

### ELEC-PAT-12: Workplaces (shop, office, industry, construction site): SRT 900/2015 protocol every 12 months
- **Rule:** in every establishment where employees work, the earthing measurement and the verification of exposed-part continuity are done with the protocol of Res. SRT 900/2015, which is valid for 12 months. If it does not comply with AEA, an action plan is drawn up to bring it into compliance. Protection against indirect contact is checked periodically.
- **Why:** Ley 19.587 and its decrees (351/79, 911/96 for construction, 617/97, 249/07) make the AEA regulations mandatory at work; the protocol leaves a uniform and verifiable record.
- **How:** the instructions require: instrument (brand, model, serial), date of its last calibration and certificate attached, date and time, method, sketch with the measurement points (items 7 to 15); for each electrode: number (22), area (23), ground condition (24), use (25: transformer neutral, safety of exposed parts, electronic equipment, IT, lighting, lightning protection, other), system earthing arrangement (26), value in Ω (27), whether it complies with AEA (28), whether the earth circuit is continuous and permanent (29), whether it has capacity for the fault current and an appropriate resistance (30), what protection against indirect contact there is (31) and whether it disconnects within AEA times (32); conclusions (40) and recommendations (41). It is signed by a professional with the competence (*incumbencia*) required in the jurisdiction. The SRT guide advises testing the RCD test button monthly.
- **Verify:** protocol current (less than 12 months), calibration certificate attached, sketch matching the actual electrodes.
- **Don't:** "renew" the protocol by copying values from the previous year; measure with an instrument without current calibration; leave out the earth of the lightning protection or of the site compound (*obrador*).
- **Source:** Res. SRT 900/2015 (BO 2015-04-28), arts. 1 to 4 and Anexo (instructions, items 1 to 41, read on argentina.gob.ar); Guía práctica SRT Res. 900/2015; Dec. 351/79, Anexo VI, item 3 (earthing circuit continuous, permanent, with current-carrying capacity for the fault current and appropriate resistance). Site compound: ELEC-PAT-20.

### ELEC-PAT-13: If the earth reads high: more depth, more well-spaced earth rods (*jabalinas*), and only then treat the soil
- **Rule:** to lower a high Ra, in this order: (1) extend the earth rod in depth (couplable rods); (2) add earth rods in parallel, preferably spaced at least twice the length of the longest one, interconnected with a conductor (preferably bare and buried) and with their connections in pits; (3) mesh or counterpoise of bare cable if the ground is rocky or shallow; (4) as a last resort, soil treatment with specific non-corrosive products. Everything within the lot and respecting the separation from the system earth (ELEC-PAT-3).
- **Why:** resistance drops mainly with depth (wetter and more stable layers are reached); doubling the diameter changes almost nothing. Two earth rods very close together share the same volume of soil and do not halve the value.
- **How:**
  - Example: 100 Ω·m soil, 5/8" × 1.5 m earth rod ≈ 61 Ω (ELEC-PAT-4). Going to 3 m (two couplable sections) ≈ 34 Ω. Adding a second 3 m rod at 6 m (2 × L): the ideal parallel would be 34 / 2 = 17 Ω, and 771 states that with that spacing the set gives on the order of 7 % more: 17 × 1.07 ≈ **18 Ω**. At 15 m (5 × L), about 3 % more (≈ 17.5 Ω). Four 3 m earth rods in a 6 m square: about 20 % more than ideal (34 / 4 × 1.20 ≈ 10 Ω); spaced 15 m, about 8 % more.
  - Check with the mutual resistance approximation for two equal electrodes (homogeneous soil, s much larger than L): R2 ≈ [R1 + ρ / (2π s)] / 2 = [34.0 + 100 / (2π × 6)] / 2 = (34.0 + 2.65) / 2 ≈ 18.3 Ω. It matches.
  - The additional earth rods are joined together with buried bare cable and exothermic or compression joints; with bare interconnection the total drops a bit more. Everything ends in a measuring pit.
  - Before designing a large electrode (building, industry), measure the soil resistivity by the Wenner method (ELEC-PAT-25).
- **Verify:** measurement after each step; record the value obtained and the final configuration on the as-built drawing (*plano conforme a obra*).
- **Don't:** pour coarse salt, charcoal with salt or homemade products (they corrode the earth rod and the effect washes out in months); drive earth rods right next to each other; look for "earth" by connecting to the neighbor's or to the building structure without a design.
- **Source:** AEA 90364-7-771 Ed. 2006, 771-C.2.2.4 note 2 (recommended spacing ≥ 2 × L; increases of 7 %, 3 %, 20 % and 8 % over the theoretical parallel; connections in pits) and 771.3 note 1 (multiple interconnected electrodes); Facbsa, "Jabalinas de acero y cobre" (copper-clad steel earth rods), Ingeniería Eléctrica, Oct 2015 (sectional earth rods and, as a last resort, chemical treatment); Fluke, "Cuatro métodos..." (doubling length lowers it by up to 40 %, doubling diameter only 10 %); mutual resistance of two electrodes: IEEE Std 142 (well-known formula, not consulted in this edition).

### ELEC-PAT-14: Earthed socket outlets (*tomas*) IRAM 2071 in the fixed installation; earthed plugs; adapters only certified and earthed
- **Rule:** in the fixed installation, 2P+T (2 poles + earth) socket outlets (*tomacorrientes*) per IRAM 2071 are fitted, 10 A (general-use circuits) or 20 A (special uses), with the earth terminal always connected to the PE. Socket outlets that accept plugs of different geometries at the same time ("biuso" or "combinados", dual-standard) and Schuko socket outlets are not installed. Class I appliances are connected with an earthed plug (*ficha*) (IRAM 2073, 10 A or 20 A). An adapter that interrupts the earth is never used.
- **Why:** the socket outlet is where the person connects to the installation; if the earth terminal is not connected or the adapter skips it, the class I appliance is left without protection against indirect contact. The 20 A IRAM 2073 plug does not fit the 10 A socket outlet on purpose, so that a high-consumption appliance is not plugged into a small circuit.
- **How:**
  - 10 A socket outlet: flat pins in a V plus earth; 20 A socket outlet: larger geometry. In dwellings, socket outlets at baseboard level or up to 0.9 m from the finished floor are 2×10+T IRAM 2071 with a shutter against the insertion of objects.
  - Current trade regime (2025): Res. SIyC 16/2025 repealed Res. 524/98. Today appliances with non-IRAM plugs may be sold if they carry the label "se requiere el uso de un adaptador certificado con toma de tierra" (the use of a certified adapter with earth is required), and adapters must have earth, comply with IEC 60884-2-5 and not accept plugs of different geometry at the same time. For installation materials, the technical regulation in force requires fixed socket outlets up to 250 V and 20 A to have an earth contact, comply with IRAM-NM 60884-1 or IEC 60884-1 and not accept plugs of different geometries simultaneously; earthed plugs may be IRAM 2073 or another IEC TR 60083 format (which includes Schuko as the plug of an imported appliance).
  - Practical conclusion: the fact that a Schuko plug may be sold with an appliance does not make it suitable for the installation. AEA requires IRAM 2071 socket outlets; if a client has appliances with a Schuko plug, use a certified earthed adapter or replace the plug with an IRAM 2073 one (done by a competent person).
- **Verify:** at each socket outlet, earth connected (socket tester or continuity to the PE) and correct polarity (see [testing-and-commissioning.md](testing-and-commissioning.md)); certification seal and QR code on socket outlets and plugs.
- **Don't:** cut or bend the earth pin of a plug; use adapters, three-way adapters (*triples*) or power strips (*zapatillas*) without earth or without certification; hang several high-consumption appliances (heater, kettle, AC) on the same three-way adapter or power strip; install dual-standard (biuso) or Schuko socket outlets in new work; plug a 20 A appliance into a 10 A socket outlet with an adapter.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.7.6 (IUG/TUG/IUE/TUE circuits with 2P+T IRAM 2071 socket outlets) and 771.8.6.2 (socket outlets up to 0.9 m in dwellings: 2×10+T IRAM 2071 with shutter, per IEC 60884-1); AEA 770 (1st ed. 2017); Res. SIyC 16/2025 (dated 2025-02-24, BO 2025-02-25), art. 8 (repeals Res. 731/87, 524/98 and 169/18), art. 2.2 (label) and Apéndice IV item 5 (adapters), per the text reproduced by derechoenzapatillas.com and Cetecom (Mar 2025); technical regulation for electrical installation materials (Disp. DNRT 2/2025, annex IF-2025-38164600-APN-DNRT#MEC, under Res. SIyC 236/2024 with the Anexo II set by Res. SIyC 26/2025), items 4.1 a) and c), per the copy published by CIRA. **Not verified in a primary source:** the text of Res. SIyC 16/2025 and of annex IF-2025-38164600 in the Boletín Oficial; the earlier ban on dual-standard (biuso) socket outlets (APSE, Ingeniería Eléctrica, Dec 2015, attributes it to a "Res. 9/2005" without it having been possible to identify the issuing body).
### ELEC-PAT-15: Buildings: one earth for the whole property, main bar on the ground floor and PE up the riser (*montante*)
- **Rule:** the building has a single protective earthing (*puesta a tierra*) system (it may have several electrodes, all interconnected), with a main earthing bar / main equipotential bonding bar on the ground floor next to the shared meter cabinet (*gabinete colectivo de medidores*) or the general panel (distribution board, *tablero*). Each line that goes up the riser (*montante*) carries its own PE together with its live conductors, and is protected against indirect contact (RCD, *ID* / *diferencial*, at the origin, or double insulation). If the utility (distribution company, *distribuidora*) has a transformer room (*cámara transformadora*) inside the building, the utility and the installer agree on how to keep the TT system by moving the electrodes apart; if a de facto TN-S still results, the installation is still designed as TT.
- **Why:** two unbonded protective earths in the same building create potential differences between exposed conductive parts that someone can touch at the same time (the countertop of an apartment (*depto*) and the landing (hallway, *palier*) railing). With a single bar and a PE in each line, everything stays at the same potential. The riser is a long run: in TT a fault to an exposed part gives only a few amperes (ELEC-PAT-1) and the line's MCB (*térmica*) does not trip.
- **How:** example case: 4-story building, apartments with single-phase supply, meters grouped on the ground floor.
  1. Earth electrode on the property's own ground, in the yard or garden; if only the garage is left, a pit with a cover rated for vehicle traffic, flush with the finished floor and outside the wheel track, never covered by the floor screed (*contrapiso*) (ELEC-PAT-5). In new construction the foundation electrode is the better choice (ELEC-PAT-24). Size it with the measured resistivity (ELEC-PAT-25); 3 m earth rods (*jabalinas*) or several in parallel are often needed (ELEC-PAT-13).
  2. Earthing conductor (≥ 4 mm² and per the table) to the main bar, where the equipotential bonding conductors from water, gas, structure and cable trays also arrive (ELEC-PAT-8).
  3. In the shared meter cabinet, next to each meter (no more than 2 m away), is the main panel (TP) of each unit, a Class II enclosure; the main line (*línea principal*) meter → main panel, short and without an RCD, is double insulated. From that main panel the **sub-main (feeder, *línea seccional*)** goes up the riser (phase + neutral + PE, in its own conduit (*cañería*)) to the apartment's sub-panel (TS, *tablero seccional*); the PE with the cross-section from the table (for example a 10 mm² line → 10 mm² PE; see ELEC-PAT-7).
  4. The sub-main in the riser is protected against indirect contact with an RCD in the unit's main panel (300 mA maximum and selective "S" if there are 30 mA RCDs downstream; in TT, sub-main circuits allow disconnection in up to 1 s), or with double insulation (sheathed cable IRAM 2178 / IRAM 62266, or single-core cables in insulating conduit and insulating boxes). See [protection.md](protection.md) (ELEC-PRO-12).
  5. In each apartment's panel, an earth bar where the PE of the sub-main and the PEs of all circuits arrive; 30 mA RCD on all final circuits (ELEC-PAT-9).
  6. Common services (*servicios generales*: landings, pumps, elevator, door entry system) are governed by AEA 90364-7-772 and use the same main bar.
  7. If the utility has a transformer room in the building: find where its earth grid is and place the protective electrode more than 10 equivalent radii away. If that cannot be achieved, it is agreed with the utility (771.5.1 and 771.5.2); if the system ends up as a de facto TN-S, it is still designed as TT, the RCDs are protected against the high fault currents that can appear, and the utility must prevent permanent touch voltages higher than 24 V from being transferred.
- **Verify:** continuity from the main bar to the earth bar of each apartment and of each common services panel; a single electrode (or interconnected electrodes) measured and recorded; no N-PE jumper in unit panels; "S" RCD or double insulation on each sub-main.
- **Don't:** let each apartment drive "its own" earth rod without bonding it to the building system; use a common "building" PE that runs from box to box with splices instead of each line's own PE; use the building's reinforcement as the only PE of the riser; take the earth from the utility transformer room's grid without a design or authorization; put an instantaneous 30 mA RCD in the main panel and another identical one in the apartment.
- **Source:** AEA 90364-7-771 Ed. 2006 (Viviendas, oficinas y locales unitarios: dwellings, offices and single shops), 771.3 note 1 (multiple interconnected electrodes), 771.5.1 (achieving the separation, with the utility's cooperation if needed), 771.5.2 (transformer substation inside the property), 771.5.3, 771.18.4 (protection against indirect contact by double insulation, 771.18.4.1, or by automatic disconnection, 771.18.4.3; table 771.18.I note 1: sub-mains in TT ≤ 1 s), 771.18.5.7 (PE inside the same wiring system as the live conductors) and 771.20.3.1 (main panel ≤ 2 m from the meter, Class II; main line double insulated); AEA 770, 770.14.3.2 b) (upstream RCD ≤ 300 mA selective) according to [protection.md](protection.md). Risers and meters: [buildings.md](buildings.md) (ELEC-EDI-6, ELEC-EDI-7, ELEC-EDI-20); panels: [panels.md](panels.md) (ELEC-TAB-20).

### ELEC-PAT-16: Elevator, pumps, tanks and metal structures: every exposed part to the PE
- **Rule:** every exposed conductive part of the building services is connected to the PE of its circuit: pump motor frames (lifting, booster, sewage, submersible), elevator panel, machine, controller, guide rails and metal structure of the shaft, pump panels, metal tanks, automatic gates. Extraneous conductive parts (metal delivery pipes, metal tanks, structures) are also bonded to the equipotential bar.
- **Why:** this is equipment with water, vibration and humidity, where insulation faults are common and where people touch metal structures (the elevator car, the tank railing).
- **How:** PE in the same cable or conduit as the supply, with the cross-section from the table; branch to the earth terminal of each motor and panel; flexible earth bonding strap on parts that vibrate or are hinged; submersible pumps with a cable that includes a protective conductor; pump and elevator circuits with their residual current protection according to the design (see [protection.md](protection.md)).
- **Verify:** continuity from the main bar to the frame of each motor and to the elevator guide rails; motor insulation (ELEC-MED-4).
- **Don't:** leave a pump's earth on the metal water pipe; bypass the pumps' RCD because "it trips when it rains" (the RCD is warning about a leakage: see [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Source:** Guía práctica SRT Res. 900/2015 (SRT practical guide; continuity of every exposed conductive part: motors, metal panels, electrical conduits, luminaires, class I machines; and extraneous conductive parts); AEA 771, 771.18.5.7 (connection of exposed conductive parts: PE in the multicore cable or in the same wiring system); AEA 90364-7-772 (Ed. 2019, common services; its text was not consulted). **Not verified in a primary source:** specific earthing requirements for the elevator in the elevator standard and in the municipal codes of each jurisdiction (the elevator maintenance company and the municipality decide their part).

### ELEC-PAT-17: Lightning protection (*pararrayos*) with its own earth, equipotentially bonded to the installation earth
- **Rule:** if the building has a lightning protection system (SPCR, series AEA 92305 / IRAM 2184), its down conductors have their own earthing, specific to that function, and that earth is equipotentially bonded to the protective earth of the electrical installation. It is recommended (not required) that the lightning protection earth not exceed 10 Ω measured with a low-frequency earth resistance tester (*telurímetro*). Where there is an SPCR, or a keraunic level of 25 or more thunderstorms per year with an overhead supply, the installation has overvoltage protection, SPD (*DPS*).
- **Why:** without bonding, during a strike a huge potential difference appears between the lightning earth and the exposed conductive parts of the installation, and it flashes over wherever it can (cables, equipment, people). Bonding does not make one earth "dependent" on the other: if the bond is cut, the lightning rod still discharges, but equipotentiality is lost. Equipotentiality matters more than the Ω value.
- **How:** SPCR electrode according to the design (AEA 92305-3 / IRAM 2184-3); bonding conductor to the main equipotential bonding bar; SPD in the main panel according to table 771.19.III; an inspection pit (*cámara de inspección*) for the lightning protection earth too.
- **Verify:** that the bond exists and has continuity; SPCR earth measurement recorded (in the SRT protocol, item 25: use "pararrayos" (lightning rod)).
- **Don't:** use the lightning rod down conductor as a PE or as the installation earth; leave the lightning rod with an isolated earth "so the lightning doesn't get into the house".
- **Source:** Guía práctica SRT Res. 900/2015, section "Puesta a tierra de sistemas de protección contra descargas atmosféricas" (earthing of lightning protection systems; own earth; the RAEA requires bonding it; ≤ 10 Ω recommended by IEC 62305 and AEA 92305; SPD with SPCR or keraunic level ≥ 25 and overhead line, table 771.19.III); instructions for Res. SRT 900/2015, item 25; Tienda AEA (AEA store; AEA 92305-1 to -4 = IRAM 2184-1 to -4, Ed. 2015). SPCR and SPD design: [special-installations.md](special-installations.md), [protection.md](protection.md) (ELEC-PRO-16) and [buildings.md](buildings.md) (ELEC-EDI-21).

### ELEC-PAT-18: Working on the earth: all sources locked out, never during a storm, never with a fault present
- **Rule:** any work on the earth electrode, the earthing conductor, the main bar or a PE is done with **all the sources** that use that earth under lockout/tagout (LOTO, *consignación*): grid, generator set, UPS, photovoltaic or hybrid inverters and batteries. Never open the test link in the pit with the installation in service, never work on earths during a thunderstorm, and never touch an earth conductor without first verifying that no current flows through it. If not everything can be locked out, the earth is not opened.
- **Why:** with an insulation fault present in some equipment, the earth conductor carries current; when the connection is opened, whoever opens it is placed in series with that current and the equipment's exposed part goes to full voltage. The main switch of the main panel does not isolate the sources that are downstream (generator set with changeover switch, UPS, inverter). During a storm, the earth can carry lightning discharge currents.
- **How:**
  1. Open the main switch, lock it, tag it and verify absence of voltage (see [site-safety.md](site-safety.md), ELEC-SEG-3 to ELEC-SEG-6). Also switch off and lock out the generator set (with automatic start disabled), the UPSs, the inverters and the batteries. In a building, lock out all the panels that use that earth bar: all units and the common services. **Danger:** if even one source is missing, the next step is not done.
  2. Before opening the earth rod clamp (*tomacable*) or the link, measure the current in the earth conductor with a **leakage clamp meter** (*pinza de fugas*; resolution of 1 mA or better; an ordinary clamp meter cannot see tens of mA): it must be zero or negligible. If there is current, do not open: there is a fault to find first.
  3. Insulating gloves and insulated tools in the pit too.
  4. When finished, reconnect, tighten and measure continuity to the bar before re-energizing.
  5. If not everything can be locked out (building in service, fire pumps), don't open the earth: measure with the selective method or with the loop method (ELEC-PAT-11).
- **Verify:** record of the lockout (with the list of sources switched off) and of the reconnection in the work schedule (*planilla de trabajo*).
- **Don't:** "measure quickly" by opening the earth with the building running; consider a building locked out because a single main switch was turned off; leave the electrode disconnected when finished; work in the pit in rain and storm.
- **Source:** Guía práctica SRT Res. 900/2015 (role of the earth in the fault loop); Dec. 351/79 and Dec. 911/96 (electrical work without voltage under Ley 19.587); AEA 771, 771-D.8 (protection must be ensured for each source that can operate alone); detailed procedure and sources that can come back: [site-safety.md](site-safety.md) (ELEC-SEG-6), UPS and inverters: [special-installations.md](special-installations.md) (ELEC-ESP-22 to ELEC-ESP-27). **Not verified in a primary source:** measuring with a leakage clamp meter before opening is good field practice, not a clause of a standard.

### ELEC-PAT-19: Maintenance: the earth is checked, not assumed
- **Rule:** the earth electrode and the earth connections are inspected and measured periodically: in workplaces, at least every 12 months (ELEC-PAT-12); in dwellings and buildings, at every renovation, whenever something changes in the ground (excavations, new paving) and after any unusual RCD (*diferencial*) trip.
- **Why:** corrosion, a covered-up pit, a loose earth rod clamp or a PE cut during a renovation give no symptoms until there is a fault.
- **How:** open the pit, check the earth rod clamp and the cable (corrosion, tightness), measure Ra (ELEC-PAT-10), measure continuity on a sample of socket outlets (*tomas*) and exposed parts, test the RCDs with a tester (ELEC-MED-6), write everything down with the date. If a protective device operated for no known reason, the installation is checked before resetting it.
- **Verify:** that the last record is less than 12 months old where it is mandatory and that the values do not show a rising trend.
- **Don't:** accept the earth as good because "it has an earth rod"; accept only the RCD's test button as proof.
- **Source:** AEA 771, 771-C.2.2.4 (periodic measurement to cover the increase in resistance due to corrosion, according to 771.23.5.2) and 771.23.6 (maintenance; check before resetting a protective device that operated for no known reason); Res. SRT 900/2015, arts. 2 and 4; Guía práctica SRT Res. 900/2015; Farina, "Puesta a tierra", Ingeniería Eléctrica, Feb 2024.

### ELEC-PAT-20: Site compound (*obrador*) and construction site panel: its own earth, measured before use
- **Rule:** the construction site panel (*tablero de obra*) has its own earth electrode (IRAM earth rod with a pit or an accessible earth rod clamp), measured before connecting tools, with all its exposed parts to the PE, a 30 mA RCD on the socket outlets and extension cords with a protective conductor. The measurement is documented with the protocol of Res. SRT 900/2015 and repeated periodically.
- **Why:** on a construction site there is water, mud, class I tools and cables that get stepped on; if the earth rod doesn't exist or is loose, the RCD is the only barrier and nobody knows it.
- **How:**
  1. The site compound's own earth rod, out of the path of machinery, respecting the separation from the system (service) earth (ELEC-PAT-3) and with a prior survey for buried services (ELEC-PAT-4).
  2. Measure Ra before putting the panel into service (≤ 40 Ω with RCD ≤ 300 mA, ELEC-PAT-9) and PE continuity to each socket outlet.
  3. Extension cords with three-conductor cable (with PE) and plugs with earth; class II tools (double insulation) where possible; in wet locations, safety extra-low voltage or an isolating transformer (ELEC-SEG-16).
  4. When the job moves to the permanent installation, the site compound's earth can be incorporated into the permanent system if it is interconnected, measured and documented.
- **Verify:** current SRT protocol for the site; test button of each RCD at the start of the workday; no cable or plug without PE.
- **Don't:** extension cords made of twin flex without earth (*cable paralelo*); drive the site compound's earth rod next to the meter pillar (*pilar*); use the reinforcement of a column as the panel's "earth"; bypass the RCD because "it trips with the concrete mixer".
- **Source:** [panels.md](panels.md) (ELEC-TAB-21: Dec. 911/96, art. 86, installation according to AEA with earthing of exposed parts and automatic disconnection) and [site-safety.md](site-safety.md) (ELEC-SEG-14 to ELEC-SEG-16); Res. SRT 900/2015; AEA 90364-7-704 Ed. 2026 (its text was not consulted). **Not verified in a primary source:** the text of Dec. 911/96, art. 86, in this review (the citation is taken from panels.md).
### ELEC-PAT-21: Generator set (*grupo electrógeno*): generator neutral to its own earth and changeover that switches the neutral
- **Rule:** when a generator set (*grupo electrógeno*) supplies the installation as an alternative to the grid (elevator, pumps, lighting of a building), the changeover does not parallel with the grid and also switches the neutral: four-pole in three-phase, two-pole (phase and neutral) in single-phase. The generator neutral is earthed to its own electrode of **10 Ω or less, separate from the public grid earth**. The exposed conductive parts of the generator and of what it supplies stay on the installation's PE, with their RCDs (*ID* / *diferencial*).
- **Why:** if the changeover does not switch the neutral, the grid and the generator are joined through the neutral, and fault or imbalance current can return through paths the RCD does not see; if the generator neutral is left floating, a fault to an exposed part does not make current flow and the RCD does not operate.
- **How:** manual I-0-II changeover switch or automatic transfer switch with interlock (ELEC-ESP-25); earth electrode for the generator neutral with its pit (*cámara de inspección*), measured and recorded; a single N-PE bonding point for the generator (at the generator or at the changeover switch, according to the design), never two (ELEC-ESP-26). A private generator allows another system (TN-S or IT) for what only it supplies, if the designer justifies it.
- **Verify:** with the generator in island mode and the grid disconnected, test the RCDs with a tester (they must trip); measurement of the generator neutral earth ≤ 10 Ω; frame-to-PE continuity.
- **Don't:** use changeover switches that switch only the phase; join the generator neutral to the utility's (*distribuidora*) neutral earth rod (*jabalina*); leave the generator neutral unearthed "because it's portable" when it supplies the fixed installation.
- **Source:** AEA 90364-7-771 Ed. 2006 (Viviendas, oficinas y locales unitarios: dwellings, offices and single shops), 771.3.2 note 2 (with a private generator, TT, TN-S or IT can be chosen) and Annex 771-D, 771-D.8 and 771-D.8.2 (protection for each source; four-pole devices in three-phase; generator neutral earthed ≤ 10 Ω, separate from the grid earth, in both single-phase and three-phase); two-pole changeover switch in single-phase: [special-installations.md](special-installations.md) (ELEC-ESP-25). Generator on a construction site: [site-safety.md](site-safety.md) (ELEC-SEG-21).

### ELEC-PAT-22: "Isolated earth" (*tierra aislada*) or "computer earth" (*tierra de informática*): separate as an electrode, never unbonded
- **Rule:** there is no separate "clean" earth for computers, servers or audio equipment. If a manufacturer or a design asks for a dedicated electrode for electronic equipment, that electrode is interconnected with the property's protective earth at the main bar; the equipment stays connected to the PE of its circuit.
- **Why:** two unbonded earths have different potentials: during a fault or a lightning strike, the difference appears between the computer case (on the "isolated earth") and any other exposed part, or between the data cable and the power cable, and it damages equipment or people. Noise is solved with a good PE, star distribution from the bar and SPDs (*DPS*), not with a loose earth.
- **How:** if a "computer earth" is requested, run a dedicated protective conductor from the main bar to the panel (distribution board, *tablero*) of that equipment (the bar is still the single bonding point); if there is an additional electrode, it is interconnected and has its pit. In the SRT protocol each electrode is identified by its use (item 25 includes "informática" (computing/IT)).
- **Verify:** continuity between the "computer earth" and the main bar; no unbonded earth rod.
- **Don't:** drive an earth rod "just for the PC" without bonding it; connect the rack's earth terminal to a pipe.
- **Source:** AEA 90364-7-771 Ed. 2006, 771.3 note 1 (multiple electrodes or additional earths in the property, all interconnected) and 771-C.2.1.1 (earthing arrangements for protective and functional purposes may be used together or separately, with protection taking priority); instructions for Res. SRT 900/2015, item 25 (use "informática").

### ELEC-PAT-23: Old installation without PE: RCD now, PE later, never an N-PE jumper
- **Rule:** in an existing dwelling or building without a protective conductor, the immediate measure is a 30 mA RCD on all circuits; afterwards the PE and the earth electrode are installed (or it is bonded to the building's). While there is no PE, do not fit three-pin socket outlets (*tomas*) that look earthed, and never join the earth terminal to the neutral.
- **Why:** the RCD protects against direct contact even without a PE, but without a PE the faulty exposed part stays energized until someone touches it; an N-PE jumper in the socket outlet puts voltage on the appliance case if the neutral breaks.
- **How:** follow the order in [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-17): RCD first, then a PE in each conduit (if it doesn't fit, rewire), earth electrode measured, equipotential bonding. In an apartment (*depto*), the PE is taken from the building's bar (ELEC-PAT-15); if the building doesn't have one, raise it with the owners' association (*consorcio*).
- **Verify:** RCD tested with a tester; once the PE is installed, continuity to each earthed socket outlet.
- **Don't:** jumper neutral and earth in the socket outlet; use the water pipe as PE; drive an earth rod for a single socket outlet without bonding it to the rest.
- **Source:** AEA 771, 771.18.3.5 (RCD ≤ 30 mA on final circuits) and 771.18.5.6 (PE throughout the installation); [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-17, ELEC-DIA-18). **Not verified in a primary source:** a mandatory upgrade regime for existing installations (it depends on the jurisdiction).

### ELEC-PAT-24: New construction: the earth electrode is decided before pouring concrete
- **Rule:** in new construction, the earth electrode is defined before digging the foundations and laying the floor screed (*contrapiso*). The 771 accepts as an electrode a bare conductor (one from the list of electrodes, e.g. 35 mm² copper) laid at the bottom of the foundation trenches, in direct contact with the soil, running around the perimeter of the building, with its ends brought to inspection pits.
- **Why:** a long perimeter electrode gives low and stable values, stays protected and takes up no yard space; after the concrete is poured it can no longer be installed.
- **How:**
  1. At the design stage: locate the main bar and the pits; leave conduit from the pits to the panel.
  2. Bare conductor at the bottom of the trench, without splices or with exothermic (*cuproaluminotérmica*) or compression joints; leads to at least two pits so it can be measured.
  3. Approximate calculation (771-C.10.2, simplified form): R ≈ 2ρ / L for about 45 m of 35 mm² conductor. *Example:* ρ = 100 Ω·m, L = 45 m: R ≈ 2 × 100 / 45 ≈ 4.4 Ω. It is verified by measurement.
  4. The structural reinforcement is equipotentially bonded (ELEC-PAT-8), but the electrode is the intended conductor, with its pits.
- **Verify:** photo and sketch (*croquis*) of the conductor in the trench before pouring (inspection before covering, ELEC-EDI-24); measurement of Ra when the job is finished.
- **Don't:** trust that "the reinforcement works as earth" without a design or a measuring point; leave the conductor without an accessible lead to a pit.
- **Source:** AEA 90364-7-771 Ed. 2006, 771-C.2.2.1 (electrodes in foundations or footings; bare conductor at the bottom of trenches running around the perimeter in new construction) and 771-C.10.2 (horizontal conductor; R ≈ 2ρ/L for about 45 m of 35 mm², 50 m of 50 mm² or 70 m of 70 mm²). **Not verified in a primary source:** rules of the 771 for using concrete reinforcement as an electrode (it does not appear in the list of electrodes consulted).

### ELEC-PAT-25: Measure soil resistivity before designing a large earth electrode (Wenner)
- **Rule:** before designing the electrode for a building, an industrial site or difficult ground, measure the soil resistivity with the Wenner method and design with that value, not with a table of "typical soils".
- **Why:** resistivity ranges from 10 to more than 1000 Ω·m depending on the soil and moisture; with the real value you choose the length and number of earth rods without trial and error.
- **How:** four test stakes (*picas*) in a line, equally spaced at a distance a, driven shallow (depth less than a/20). The earth resistance tester (*telurímetro*) injects through the outer ones and measures between the inner ones: ρ = 2π · a · R. Repeat with several spacings (a ≈ the depth you are interested in: 1.5 m, 3 m, 6 m) and in two directions.

  *Worked example:* a = 3 m, reading R = 5.3 Ω: ρ = 2π × 3 × 5.3 ≈ 100 Ω·m. With that value, one 5/8" × 3 m earth rod gives ≈ 34 Ω (ELEC-PAT-4).
- **Verify:** schedule (*planilla*) with a, R, calculated ρ, direction, date and soil condition.
- **Don't:** measure with the stakes over a buried pipe or parallel to it; use a value from a rainy day as if it were the year-round value.
- **Source:** Wenner method (widely published formula; IEEE Std 81); Farina, "Sistema de puesta a tierra", Ingeniería Eléctrica, Feb 2022 (typical resistivities and Wenner); AEA 95501-2 / IRAM 2281-2 Ed. 2021 (its text was not consulted).

### ELEC-PAT-26: Antennas, coaxial, door entry system and equipment on the facade: all to the same earth
- **Rule:** antenna masts, the coaxial cable shield at the entry, door entry or video entry equipment (*portero* / *videoportero*) with a class I power supply, low-current cable trays and outdoor air conditioner (AC) units on the facade or balcony are connected to the PE or to the building's equipotential bar. None of them has its own unbonded earth rod.
- **Why:** this equipment is outdoors or comes in from outside, and it suffers the most from lightning strikes and overvoltages; if it is on a different earth, the potential difference appears on the signal cable or on the case that someone touches from the balcony.
- **How:** mast with a bonding conductor to the equipotential bar (or to the SPCR if there is one, ELEC-PAT-17); coaxial shield bonded at the building entry; outdoor AC unit with the PE inside the supply cable from the apartment's panel (ELEC-ESP-11); door entry power supply to the PE of its circuit.
- **Verify:** continuity between the mast, the outdoor unit case and the bar; no isolated earth rod on the roof terrace or balcony.
- **Don't:** leave the mast "earthed" to an unbonded earth rod on the roof terrace; hang the outdoor AC unit without a PE.
- **Source:** AEA 771, 771.18.5.7 (all metal parts of the installation to the PE) and 771.3 note 1 (single interconnected electrode); [buildings.md](buildings.md) (ELEC-EDI-17). **Not verified in a primary source:** the earthing standard for antennas and cable networks (IEC 60728-11).

### ELEC-PAT-27: Installations that involve earthing: photovoltaic, EV charger, pool, electric shower
- **Rule:** each of these installations uses the same earth electrode of the property and adds the requirements of its own section: frames and structures of photovoltaic panels bonded to the PE and the inverter with the RCD its manufacturer requires; the circuit of an electric vehicle charging point with its PE, without a PEN conductor; pool with its equipotential bonding; electric shower and water heater with PE and a dedicated circuit.
- **Why:** these are loads with water, power electronics or outdoors; a missing PE or a separate earth makes them dangerous, and some (inverters, chargers) can put direct current into the fault and blind a type AC RCD.
- **How:** photovoltaic: [special-installations.md](special-installations.md) (ELEC-ESP-20 to ELEC-ESP-24); charger: ELEC-ESP-17 and ELEC-ESP-18 (the control signals the charger uses over the PE must not pass to the fixed installation upstream); pool: ELEC-ESP-7 to ELEC-ESP-9; shower and water heater: ELEC-ESP-6. RCD type: ELEC-ESP-2.
- **Verify:** PE continuity to the frames, inverter case, charger, pool pump and shower; test of the corresponding RCD.
- **Don't:** drive a separate earth rod for the panels or the charger without bonding it; supply an electric shower without PE.
- **Source:** AEA 90364-7-722 Ed. 2024 (2nd ed. text dated 2023), 722.312.2.1 (no PEN in charging point circuits in TN) and 722.543.101 (control signals on the PE); AEA 771, 771.3 note 1; details and sources in [special-installations.md](special-installations.md).

### ELEC-PAT-28: Earth symptoms: neutral-earth voltage, "kicks" (*patadas*) and RCD that trips with rain
- **Rule:** three symptoms point to the earth or the PE and are treated as a risk, not a nuisance: (1) voltage between neutral and PE at a socket outlet or in the panel; (2) a "kick" (*patada*) or tingle when touching a tap, a fridge or a railing; (3) an RCD that trips when it rains.
- **Why:** in TT a few volts between N and PE are normal (it is the voltage drop on the grid neutral); tens of volts indicate a degraded or broken neutral. The kick is a live exposed part that is not discharging to earth. The RCD that trips with rain is seeing a real leakage (water in an outdoor box, a pump, a buried cable).
- **How:**
  - N-PE voltage: measure it at the main panel and at the socket outlet; from 0 to a few volts, normal; tens, see [testing-and-commissioning.md](testing-and-commissioning.md) (ELEC-MED-21) and broken (lost) neutral (*corte de neutro*) in buildings (ELEC-DIA-14).
  - Kick: switch off the main switch and follow ELEC-DIA-16 (PE, Ra, insulation, equipotential bonding).
  - RCD with rain: look for the leakage circuit by circuit with a megohmmeter (megger, *megóhmetro*) (ELEC-DIA-4) and check outdoor boxes, pumps and the gate; never bypass the RCD.
- **Verify:** that after the repair the exposed part has no voltage with respect to earth, Ra is within the table and the RCD trips with a tester.
- **Don't:** join neutral and earth to "lower" the N-PE voltage; keep using the appliance that gives a kick; remove the pump's RCD "because it trips with rain".
- **Source:** [testing-and-commissioning.md](testing-and-commissioning.md) (ELEC-MED-21) and [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-4, ELEC-DIA-14, ELEC-DIA-16); AEA 771, 771.23.6 (operation of a protective device for no known reason: check before resetting). **Not verified in a primary source:** a regulatory threshold for N-PE voltage ("a few volts" and "tens" are practical criteria).

## Earthing checklist for a job
| # | Item | Rule |
|---|---|---|
| 1 | TT system confirmed (LV supply) or written justification for another system | ELEC-PAT-1 |
| 2 | No N-PE jumper in the user's installation | ELEC-PAT-2 |
| 3 | Protective electrode within the property, > 10 equivalent radii from the system (service) earth | ELEC-PAT-3 |
| 4 | Buried services located before driving rods or trenching | ELEC-PAT-4 |
| 5 | IRAM earth rod (*jabalina*) with engraved marking (minimum JL14 × 1500); buried joints welded or compressed | ELEC-PAT-4 |
| 6 | Accessible inspection pit with earth rod clamp (*tomacable*) or test link | ELEC-PAT-5 |
| 7 | Earthing conductor ≥ 4 mm² and per the table, insulated, to the main panel | ELEC-PAT-6 |
| 8 | PE at all outlet points (*bocas*), cross-section from the table, no daisy-chaining (*guirnalda*) | ELEC-PAT-7 |
| 9 | Extraneous conductive parts (water, gas, structure, cable trays) bonded; bathrooms according to 701 | ELEC-PAT-8 |
| 10 | Measured Ra ≤ 40 Ω (or the table value for the RCD); 30 mA RCD on all final circuits | ELEC-PAT-9, ELEC-PAT-10 |
| 11 | IRAM 2071 socket outlets with earth connected; no dual-standard (*biuso*) or Schuko | ELEC-PAT-14 |
| 12 | Building: single main bar, PE on each line in the riser (*montante*), "S" RCD or double insulation | ELEC-PAT-15 |
| 13 | Elevator, pumps, tanks, antennas and outdoor units to the PE | ELEC-PAT-16, ELEC-PAT-26 |
| 14 | Lightning protection (*pararrayos*) with its own bonded earth; SPD if applicable | ELEC-PAT-17 |
| 15 | Generator set: changeover that switches the neutral, and neutral earth ≤ 10 Ω | ELEC-PAT-21 |
| 16 | Record of measurements with date, method, instrument and ground condition | ELEC-PAT-10, ELEC-PAT-12 |

## What this guide does not replace
- The design, the earthing calculation and the sign-off of the installation are done by a professional or qualified electrician (installer) with the category the jurisdiction requires (see [regulations-and-permits.md](regulations-and-permits.md)).
- The full text of the Reglamentación AEA (AEA wiring regulations) and of the IRAM standards: here they are summarized and cited; when in doubt, your current copy rules.
- The utility decides its part (meter pillar, system earth, transformer room); the municipality, building and elevator matters; the gas utility, the gas piping.
- In a workplace, the measurement is legally valid only with the SRT protocol signed by someone with the professional scope (*incumbencia*) for it.
