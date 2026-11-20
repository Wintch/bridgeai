---
title: Measurements, tests and commissioning
scope: initial and periodic verification of low-voltage installations in buildings in Argentina (dwellings, offices, shops, apartment buildings); visual inspection, continuity, insulation, earthing, RCDs, polarity, loop impedance and prospective short-circuit current, leakage, thermography, SRT 900/2015 protocol, handover documentation, staged energization, extensions and periodic verification
when_to_use: before energizing a new or refurbished installation; when connecting an extension; when handing over a job; when a shop, office or owners' association needs the annual earthing protocol; in the periodic inspection of an existing installation; when instruments have to be chosen or checked; when a test gives an odd value
related: [README.md, regulations-and-permits.md, grades-and-circuits.md, conductors-and-conduits.md, protection.md, earthing.md, panels.md, buildings.md, site-safety.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md]
as_of: 2026-11-15
sources: [AEA 90364-6 Verificación de las instalaciones eléctricas (Ed. 2025, according to the AEA store; its text was not consulted), AEA 90364-7-771 (Ed. 2006 and corrigenda), AEA 90364-7-770 (Ed. 2017 with Corrigendum 1 of Aug 2018, clause 770.19.5.2.1; Ed. 2026 digital on sale, print in pre-sale), Res. SRT 900/2015 (BO 2015-04-28) with annex and instructions, Guía práctica SRT de interpretación de la Res. 900/2015 (SRT practical interpretation guide, with AEA collaboration), Manili and García del Corro, Ingeniería Eléctrica 305 (Dec 2015), IEC 60364-6:2016, IEC 61008-1, IEC 62423, IEC 61557 series, IEC 61010-1, Subanexo 4 Normas de Calidad del Servicio Público (RTI 2017-2021, Edenor/Edesur), Res. ENRE 225/2011 and 269/2012 (DCI), Res. CPIQ 4/2025 (BO 2025-11-25)]
---
# Measurements, tests and commissioning

How to verify an installation before energizing it and how to hand it over. Each rule has an ID (`ELEC-MED-n`) so that
the agent, a report or a message can cite it ("ELEC-MED-6 missing: the RCD was only tested with the button"). Numerical values
carry their source; where a value could not be confirmed in a primary source, this is stated.

For calculations (voltage drop, permissible loop impedance, resistance of a conductor, maximum Ra, short-circuit
current) the agent uses the offline calculator `gateway electricidad ...` (current, voltage drop, cross-section,
demand/grade, coordination, earthing) and does not calculate from memory. The worked examples in this guide help to understand the
calculation and to check the result.

**Safety first.** Dead tests (continuity, insulation, earth with an earth resistance tester (*telurímetro*)) are done with the installation
under lockout/tagout (LOTO, *consignación*): switched off, locked, verified dead and tagged (see [site-safety.md](site-safety.md)). The
tests that need voltage (RCDs (*disyuntor* / *diferencial*), loop, voltage at socket outlets, leakage, thermography) are measurements on an energized
installation: only a trained person does them, with an instrument of the correct category and PPE (*EPP*). Never do live
work (connecting, tightening a terminal, removing a cable).

## Current edition of the standards (as of 2026-11-15)
| Document | Edition | What we use it for here | Source |
|---|---|---|---|
| AEA 90364-6, Verificación de las instalaciones eléctricas (verification of electrical installations) | 2025 (3rd ed.) | List of inspections and tests, methods, initial and periodic verification | AEA store (aea.org.ar/tienda-aea), consulted 2026-11-15 |
| AEA 90364-7-771, Viviendas, oficinas y locales (unitarios) (dwellings, offices and single shops) | 2006 + corrigenda | Buildings, offices, shops and dwellings outside the scope of 770 | AEA store; SRT Res. 900 guide ("versión 2006") |
| AEA 90364-7-770, Viviendas unifamiliares con consumos hasta 63 A inclusive y corriente presunta de cortocircuito ≤ 10 kA (BA2, BD1) (single-family houses) | Ed. 2017 + Corrigendum 1 (2018), which is the one used here. Ed. 2026: the digital version is already on sale in the AEA store and the print version is in pre-sale (delivery announced from 2026-11-16), with no published effective date (AEA store, 2026-11-15) | Simple single-family house. Corrigendum 1 set the insulation minimums aligned with IEC 60364-6 | AEA store; Corrigendum 1 (published by GCBA) |
| AEA 90364-7-772, Espacios comunes y servicios generales (common areas and common services) | 2019 | Common services of a building | AEA store |
| AEA 90364-7-704, Obras, demoliciones (construction and demolition sites) | 2026 | Construction site panel | AEA store |
| IEC 60364-6, Verification | 2016 | International basis of AEA Part 6: insulation table, test sequence, cold Zs criterion | IEC text (not re-consulted in this session) |
| IEC 61008-1 (RCDs without overcurrent protection) | Ed. 4.0, 2024 | Tripping currents and times of the RCD | AFNOR/VDE listing of IEC 61008-1:2024 |
| Res. SRT 900/2015 | In force, no amendment found | Annual protocol for earthing and continuity of exposed conductive parts in workplaces | Boletín Oficial 2015-04-28 |

> A 4-story building with apartments and common services falls under 771 (units) and 772 (common areas). 770 is
> only for the single-family house up to 63 A and 10 kA. The clause numbering of Part 6 cited below (612/613) is that
> of the previous edition cited by AEA in 2015. It may have changed in Ed. 2025: check the number in your copy.

## Quick reference
| Test | Live or dead | Instrument (instrument standard) | Acceptance criterion | Rule |
|---|---|---|---|---|
| Visual inspection | Dead | Eyes, drawings, flashlight | ELEC-MED-2 list complete | ELEC-MED-2 |
| Continuity of the PE (circuits and sub-mains) and equipotential bonding | Dead | Low-resistance ohmmeter, ≥ 0.2 A, 4 to 24 V open-circuit (IEC 61557-4) | Every exposed conductive part and every earth terminal connected; value consistent with length and cross-section | ELEC-MED-3 |
| Insulation resistance | Dead, incoming switch open on all poles | Megohmmeter (IEC 61557-2) | ≥ 1 MΩ at 500 V DC on 220/380 V circuits (including MBTF); ≥ 0.5 MΩ at 250 V DC on MBTS/MBTP | ELEC-MED-4 |
| Earth electrode resistance (TT) | Earth resistance tester: dead, before energizing. Loop method: live, after energizing | Earth resistance tester (IEC 61557-5) or loop tester (IEC 61557-3) | Ra ≤ value in table 771.3.I for the IΔn used (max. 40 Ω with RCD ≤ 300 mA) | ELEC-MED-5 |
| RCDs | Live | RCD tester (IEC 61557-6) | Sinusoidal: does not trip at 0.5 IΔn; trips between 0.5 and 1 IΔn; ≤ 300 ms at IΔn; ≤ 150 ms at 2 IΔn; ≤ 40 ms at 5 IΔn (general type) | ELEC-MED-6 |
| Polarity and phase sequence | Dead (ohmmeter) and confirmation live | Ohmmeter, multimeter, phase sequence tester (IEC 61557-7) | Switches and lampholders on the phase; phase on L; correct sequence in three-phase circuits | ELEC-MED-7 |
| Voltage at socket outlets and drop | Live | CAT III multimeter | Mains voltage within ±8 % (Edenor/Edesur area); circuit drop consistent with the calculated value | ELEC-MED-8 |
| Phase-PE loop impedance (TN, or to bound Ra in TT) | Live | Loop tester (IEC 61557-3) | Zs ≤ U0 / Ia; measured cold, ≤ 2/3 of that value | ELEC-MED-9 |
| Prospective short-circuit current | Live | L-N loop tester, PSC/PFC function (IEC 61557-3) | Breaking capacity of each device ≥ maximum prospective Icc of the panel | ELEC-MED-17 |
| Leakage current per circuit or per RCD | Live, under load | Leakage clamp meter (resolution ≤ 0.01 mA) | Sum per RCD ≲ 0.3 IΔn (≈ 9 mA for 30 mA) | ELEC-MED-18 |
| Emergency lights and SPD | Live | Cutting the circuit, clock; SPD indicator window | Light up instantly; autonomy ≥ 1.5 h; SPD reconnected and showing "ok" | ELEC-MED-22 |
| Panel thermography | Live, under load | Thermal camera | No hot spots outside the criteria of ELEC-MED-23 | ELEC-MED-23 |
| Test with the RCD's test button | Live | The RCD's own button | Trips | ELEC-MED-15 (use, not a test) |

## Rules

### ELEC-MED-1: Order of tests: look first, then dead tests, live tests last
- **Rule:** always follow this order: 1) visual inspection; 2) continuity of protective conductors and equipotential bonding (with the same phase-PE jumper, polarity is checked dead, ELEC-MED-7); 3) insulation resistance; 4) earthing with the earth resistance tester (*telurímetro*); 5) only then energize in stages (ELEC-MED-12) and do: polarity confirmation, loop and prospective short-circuit current (if you measure Ra by the loop method, it goes here), RCDs, voltage and drop, leakage and functional tests. Thermography goes last, under load. If a test fails, correct it and repeat that test and the ones that depend on it.
- **Why:** live tests make current flow through the PE (the RCD tester injects current from phase to earth). If the PE is broken, the exposed conductive parts become live during the test. And energizing with a short circuit or damaged insulation is a bolted fault in the face of whoever switches on.
- **How:** write each result in the schedule (*planilla*) as you measure (see the model record in "Test record: 4-story building case"). Don't move to the next stage with an open item.
- **Verify:** the schedule has the date and value of tests 1 to 4 before the time of the first energization.
- **Don't:** test the RCD (*diferencial*) "to see if it works" before having measured PE continuity; energize "for a moment" to look for an insulation problem.
- **Source:** order adapted from the test list of AEA 90364-6, 613.1 (continuity → insulation → MBTS/separation → floors and walls → automatic disconnection, which includes the measurement of Ra → additional protection → polarity → phase order → functional → voltage drop), according to Manili and García del Corro, *Ingeniería Eléctrica* 305, Dec 2015 (edition of Part 6 prior to the 2025 one), and from IEC 60364-6:2016, 6.4.3 (test sequence; polarity appears as a test that can be done dead). The grouping into "dead / live" is good practice of this guide, not a literal clause.

### ELEC-MED-2: Complete visual inspection before measuring
- **Rule:** before any measurement, walk through the installation with the drawings and the list below. What looks wrong is not "compensated" by a good measurement.
- **Why:** many dangerous faults do not show up on any instrument: a PE of insufficient cross-section that still gives continuity, a wrongly chosen RCD, a PIA (MCB, *térmica*) with insufficient breaking capacity, a box without a cover, a panel without a sign.
- **How:** minimum list (summary of AEA 90364-6, 612.2, adapted to the job site):
  1. Protection: each circuit with its two-pole PIA with a rating matching the cross-section (In ≤ Iz of the conductor, ELEC-PRO-4); breaking capacity of each PIA and of the incoming switch ≥ prospective Icc at that panel (utility data or calculation, confirmed with the measurement of ELEC-MED-17; ELEC-PRO-3); RCD with IΔn ≤ 30 mA on lighting and socket-outlet circuits up to 32 A, with a rated current matching the PIAs below it (ELEC-PRO-10); two-pole (single-phase) or four-pole (three-phase) incoming switch in the main panel (see [protection.md](protection.md)).
  2. Conductors: cross-sections according to the design; colors (green-yellow only for PE, light blue for neutral); PE in all circuits; no splices outside boxes; cables suitable for conduit (no flexible cord (*tipo taller*) embedded in walls).
  3. Wiring systems: conduits with their fill ratio, boxes with covers, no conductors exposed outside conduit or cable tray; passages between floors sealed (fire barriers).
  4. Panels (*tableros*): enclosure, inner cover (dead front, *contratapa*), IP rating according to the location, identification of each circuit, separate neutral and earth bars, earth terminal of the metal cabinet connected, electrical hazard signs (see [panels.md](panels.md) and [reviewing-a-panel.md](reviewing-a-panel.md)).
  5. Earthing: earth rod (*jabalina*) with its accessible inspection pit, earthing conductor with the minimum cross-section, main equipotential bonding (metal water and gas pipes, structure, cable trays) to the bar; supplementary bonding in bathrooms (see [earthing.md](earthing.md) and [special-installations.md](special-installations.md)).
  6. Socket outlets and outlet points (*bocas*): socket outlets with an earth terminal (IRAM 2071, 10 A and 20 A), switches in the phase conductor, nothing broken or burnt, heights and bathroom zones respected.
  7. Isolation and switching: each panel and each circuit can be switched off; panels accessible.
  8. Documentation: single-line diagram (*unifilar*) in the panel or at hand, drawings up to date.
- **Verify:** the list signed and dated, with each item marked "ok", "corrected" or "not applicable".
- **Don't:** skip the inspection "because we did the installation ourselves"; accept adapters, multi-plug adapters or power strips (*zapatillas*) as part of the fixed installation.
- **Source:** AEA 90364-6, 612.2 (inspection list), summarized in *Ingeniería Eléctrica* 305 (Dec 2015). Requirement for RCD ≤ 30 mA on lighting and socket-outlet circuits up to 32 A and a two-pole/four-pole circuit breaker with protection on all poles in the main panel: Guía práctica SRT Res. 900/2015 (SRT practical guide), citing AEA 90364-7-771 Ed. 2006. Breaking capacity ≥ prospective Icc: AEA 90364-7-770 Ed. 2017, 770.15.2.2.2 (see ELEC-PRO-3).

### ELEC-MED-3: Continuity of the protective conductor and of the equipotential bonding connections
- **Rule:** measure PE continuity in three sections: (a) of each circuit, from the panel's earth bar to each exposed conductive part (cabinets, metal luminaires, class I appliances, metal pipes) and to the earth terminal of each socket outlet; (b) of each sub-main (feeder) or riser (*montante*), from the earth bar of each sub-panel (TS, *tablero seccional*) to the main earth bar; (c) of each equipotential bonding connection (water, gas, structure, cable trays, and the supplementary bonding in bathrooms) to its bar. Use a low-resistance instrument that delivers at least 200 mA with 4 to 24 V open-circuit.
- **Why:** without a continuous PE, the RCD does not see the fault until a person closes the circuit, and during the RCD test the exposed conductive parts become live. An ordinary multimeter (milliamperes) shows "continuity" through a single copper strand or a loose terminal that cannot carry a fault current. In a building, a break in the PE of the sub-main leaves a whole unit without earth, and the per-circuit method does not see it because the jumper is made in the sub-panel itself.
- **How:**
  1. Installation under lockout/tagout (dead, locked, verified).
  2. Zero the instrument leads (lead compensation) before starting, including the long test lead if you use it.
  3. Practical per-circuit method: at the panel, temporarily jumper the circuit's phase to the PE; at each outlet point and socket outlet, measure between phase and earth. The value is R1 + R2 (phase + PE); the farthest point gives the maximum. Remove the jumper when finished (note it in the schedule: a forgotten jumper is an earth fault).
  4. Sub-mains and risers (building): with a long, compensated test lead, measure between the earth bar of each sub-panel and the building's main earth bar (in the meter cabinet or meter room, or the main equipotential bar). Compare with R = r × L of the line's PE.
  5. Equipotential bonding: measure between the main equipotential bar and each connected element. In bathrooms and wet rooms, between the terminal or bar of the supplementary bonding and each bonded metal part (pipes, metal bathtub or shower tray, grates), and from there to the circuit's PE (see ELEC-ESP-5 in [special-installations.md](special-installations.md)).
  6. Compare with the expected value: R = r × L, with r the resistance per meter of the conductor.

  | Cross-section (mm²) | Class 5 copper (flexible, the typical single-core site cable), mΩ/m at 20 °C | Class 1/2 copper (solid or stranded), mΩ/m at 20 °C |
  |---|---|---|
  | 1.5 | 13.3 | 12.1 |
  | 2.5 | 7.98 | 7.41 |
  | 4 | 4.95 | 4.61 |
  | 6 | 3.30 | 3.08 |
  | 10 | 1.91 | 1.83 |

  *Worked example (circuit):* socket-outlet circuit in 2.5 mm² (class 5), farthest socket outlet at 22 m of cable from the panel. R2 (PE only) = 22 m × 7.98 mΩ/m = 0.176 Ω. With the phase-PE jumper you measure R1 + R2 = 2 × 0.176 = 0.35 Ω. If you measure 0.36 Ω, it is fine; if you measure 1.8 Ω, there is a loose terminal or a bad splice even though "there is continuity".

  *Worked example (4th-floor sub-main):* 10 mm² class 5 PE, 25 m from the main earth bar to the sub-panel. R = 25 m × 1.91 mΩ/m = 0.048 Ω. Measuring about 0.05 to 0.07 Ω is normal (the terminals add up). With 0.5 Ω there is a bad splice or terminal in a junction box or in the cabinet.
- **Verify:** every exposed conductive part and every earth terminal with a reading; no value far above the expected one for its length; each sub-panel with its line PE measured; equipotential bonding connections with low values similar to each other. A lack of continuity breaches the AEA rules. In workplaces, it is also recorded in the SRT 900/2015 protocol (field "circuito de puesta a tierra continuo y permanente" (continuous and permanent earthing circuit)) and requires an action plan (art. 3).
- **Don't:** use metal conduit or the structure as the only PE; measure with the multimeter in "beep" mode; leave test jumpers in place; accept an apartment's earth by measuring only from its own panel.
- **Source:** instrument ≥ 200 mA, 4 to 24 V: Guía práctica SRT Res. 900/2015 (section "Continuidad de las masas", citing AEA and IEC 61557-4) and AEA 90364-6, 613.2 according to *Ingeniería Eléctrica* 305. Continuity of all protective conductors, including those of the distribution lines: IEC 60364-6:2016, 6.4.3.2. Res. SRT 900/2015, art. 1 (scope: workplace) and art. 3 (action plan when any exposed conductive part is not connected to earth). Resistances per meter: IEC 60228 (maximum values at 20 °C, published by manufacturers). **Not verified in a primary source:** a numerical continuity limit in Part 6 Ed. 2025 (AEA does not set a single value in the sources consulted; "consistent with length and cross-section" is the IEC 60364-6 criterion); the number of that field in the SRT annex (from its position between items 28 and 30 cited by the Guide, it would be 29; the official annex is an image and could not be read).
### ELEC-MED-4: Insulation resistance with a megohmmeter (*megóhmetro*)
- **Rule:** measure the insulation of each circuit, with the incoming switch open on all poles and the current-using equipment disconnected, between live conductors (phase-neutral, phase-phase) and between the live conductors joined together and the PE. Test voltages and minimums:

  | Circuit | Test voltage (DC) | Minimum resistance |
  |---|---|---|
  | MBTS / MBTP (SELV/PELV: extra-low voltage with protective separation, e.g. 12 V in a bathroom or pool) | 250 V | 0.5 MΩ |
  | Up to 500 V (220 V single-phase, 380 V three-phase), including MBTF (FELV, functional extra-low voltage without protective separation) | 500 V | 1 MΩ |
  | Over 500 V | 1000 V | 1 MΩ |
  | Circuit with an SPD that cannot be disconnected (e.g. socket outlets with a built-in SPD (*DPS*)) | 250 V | 1 MΩ |

- **Why:** low insulation means leakage current (RCD (*disyuntor* / *diferencial*) trips with no visible cause, consumption), fire risk and contact risk. Insulation damaged while pulling the cables through the conduit cannot be seen, but the megohmmeter finds it. And the measurement is only valid if the live conductors are floating with respect to earth: in TT the utility's neutral is earthed at the transformer (Rb), so with the incoming switch closed and the supply connected, the "L+N to PE" measurement closes through Rb, the earth and Ra, and gives a few ohms or kΩ: a false "fails".
- **How:**
  1. Put the installation under lockout/tagout (LOTO, *consignación*) (ELEC-MED-14). Warn everyone: the megohmmeter applies 500 V DC and can give a shock.
  2. **Open the two-pole or four-pole incoming switch (all-pole disconnection, neutral included) of the panel you are going to insulation-test.** This way the installation is separated from the utility's neutral and from the meter. Switching off only the circuit's MCB (*térmica*) is not enough. Never insulation-test upstream of the main panel's incoming switch or the meter: that belongs to the utility (*distribuidora*), and the megohmmeter would apply 500 V DC to the meter's voltage circuit and to the SPDs. In a building: confirm that the unit's neutral is not joined to the neutral bar of another unit or to the common services one.
  3. Disconnect everything that can be damaged or distort the reading: electronic equipment, power supplies, LED drivers, electronic ballasts, dimmers, timers, photocells, motion sensors, relays and contactors with a connected coil, doorbells, and the SPDs of the main panel and the sub-panels. Remove lamps or open their circuits.
  4. RCDs (*diferenciales*): electromechanical RCDs can be left closed to measure live conductors joined together against PE, but RCDs or switches with electronics (and some with indicators) can be damaged or distort the reading between phase and neutral: when in doubt, open the RCD and measure upstream and downstream separately, or follow the manufacturer's manual.
  5. With the incoming switch open, the PIAs closed and the equipment disconnected, measure: phase-neutral; phase and neutral joined against PE. In three-phase: between phases, phases-neutral and all against PE.
  6. Sub-main (building): with the incoming switch of the unit's main panel and that of the sub-panel open, measure the line's conductors against each other and against PE.
  7. Hold the voltage until the reading stabilizes (on the order of one minute; the instrument indicates it) and let the instrument discharge the circuit before touching the conductors.
  8. Reconnect everything that was disconnected (SPDs included) and note it.

  *Worked example (why measure per circuit):* if you measure the whole panel with 8 circuits in parallel, each of 50 MΩ, the instrument shows R = 1 / (8 × 1/50 MΩ) = 6.25 MΩ. If one had 1.2 MΩ (just above the minimum, suspicious), the total would be 1 / (7/50 + 1/1.2) = 1.03 MΩ and you would not know which one it is. Measuring per circuit, it shows up at once.
- **Verify:** each circuit equal to or greater than the minimum in the table. Real values in a new installation are usually much higher (tens or hundreds of MΩ); if a circuit gives much less than the others, investigate even if it exceeds the minimum.
- **Don't:** insulation-test with the incoming switch closed and the supply connected; insulation-test with electronic equipment or SPDs connected; insulation-test a live circuit; touch probes or conductors during the test or before discharge; accept "1.1 MΩ" on a new circuit when the others give 200 MΩ without looking for the cause (moisture in boxes, pinched cable, dirty terminal).
- **Source:** AEA 90364-7-770 Ed. 2017, Corrigendum 1 (August 2018), clause 770.19.5.2.1 and table 770.19.I, which AEA adopted "considerando los valores mínimos ... de la nueva edición de la norma IEC 60364-6" (considering the minimum values ... of the new edition of the IEC standard) (text published by GCBA). IEC 60364-6:2016, table 6.1: SELV and PELV 250 V / 0.5 MΩ; up to 500 V "including FELV" 500 V / 1 MΩ; over 500 V 1000 V / 1 MΩ; with a non-disconnectable SPD, 250 V and ≥ 1 MΩ (6.4.3.3). Measurement between live conductors and PE with the installation separated from the supply: IEC 60364-6, 6.4.3.3. **Not verified in a primary source:** the literal wording of the extra-low-voltage row in table 770.19.I (if it said "MBTF", MBTF is still tested as in IEC: at 500 V with ≥ 1 MΩ); the verification clause of AEA 90364-7-771 Ed. 2006 (earlier versions used less demanding criteria). Since Part 6 Ed. 2025 and 770 are aligned with IEC 60364-6, use 1 MΩ at 500 V as the criterion under 771 too.

### ELEC-MED-5: Earth electrode resistance: measure, compare with the table and record
- **Rule:** in a TT system (the one of every low-voltage supply from the public grid) measure the resistance of the protective earth electrode (Ra) and verify that it does not exceed the maximum in table 771.3.I for the IΔn of the protecting RCD. With an RCD up to 300 mA, the maximum allowed by AEA (column 3 of table 771.3.I) is 40 Ω, and it is the value against which items 27 and 28 of the SRT protocol are filled in. The method, the placement of the earth resistance tester's auxiliary rods or stakes, and the difficult cases are in [earthing.md](earthing.md).
- **Why:** in TT the voltage that appears on a faulty exposed conductive part is Id × Ra. The table limits Ra so that, with the RCD tripping, the exposed part does not rise above 24 V (conventional limit voltage set by the decrees of Ley 19.587 and adopted by AEA).
- **How:**
  1. Usual option: earth resistance tester (*telurímetro*, IEC 61557-5) by the fall-of-potential method, with the earth rod (*jabalina*) disconnected from the earthing conductor while you measure (installation under lockout/tagout; reconnect it and note it). This is done dead, before energizing.
  2. Option accepted by AEA: measure the phase-PE fault loop impedance with a loop tester. This is done live, in the live-testing stage and after verifying PE continuity. It includes Rb (the utility's neutral earth), so it gives a higher value than Ra: if it is still below the maximum, Ra complies and is reported as "Ra < measured value".
  3. The earth clamp meter (stakeless) does not work for a single earth rod of a house or building in TT: it needs a loop of several earths in parallel (ELEC-PAT-11).
  4. Note the soil condition (dry, wet, recent rain), electrode number according to the sketch (*croquis*), use of the electrode and earthing system (item 26 of the SRT protocol). These are protocol fields.

  *Worked example:* theoretical condition Ra × IΔn ≤ 24 V. With IΔn = 30 mA: Ra ≤ 24 V / 0.03 A = 800 Ω; with IΔn = 300 mA: Ra ≤ 24 V / 0.3 A = 80 Ω. Column 3 of table 771.3.I sets lower values: with an RCD up to 300 mA, maximum Ra 40 Ω. According to the SRT Guide (written with AEA), the margin is "para tomar las diferentes variaciones ocasionales" (to account for the various occasional variations) of the electrode value, for example seasonal changes in the soil. A value of 12 Ω measured in winter with wet soil complies, but record the soil condition: in a dry summer it can rise. Useful fact: Ed. 2006 of 771 raised the maximum from 10 to 40 Ω; if someone still asks for "10 Ω", it is a requirement of the previous regulation (or a design requirement).
- **Verify:** measured value and method noted in the schedule, with date and soil condition; Ra ≤ the table maximum for the installed RCD. In TN-S (only with a dedicated transformer): system earth Rb ≤ 2 Ω, and preferably ≤ 1 Ω.
- **Don't:** measure with the earth rod connected to the installation and "believe" the earth resistance tester's number (you are measuring in parallel with other earths); measure a single earth rod with a clamp; use the lightning protection earth as the protective earth without the equipotential bonding that AEA requires; bond the protective earth to the neutral in a TT system.
- **Source:** Guía práctica SRT Res. 900/2015 (SRT practical guide): table 771.3.I, column 3, "se establecen como máximos" (are set as maximums) and "deben ser respetados para completar los puntos 27 y 28 del protocolo" (must be respected to fill in those protocol items); 40 Ω as "el máximo valor permitido por la RAEA para el ECT TT" (the maximum value allowed by the RAEA for the TT earthing system) with IΔn ≤ 300 mA; item 26 (ECT); earth resistance tester and fault loop methods; Rb ≤ 2 Ω in TN-S; limit voltage 24 V according to Decrees 351/79, 911/96, 617/97 and 249/07. AEA 90364-7-771 Ed. 2006, clause 771.3 and table 771.3.I (see the table in the regulation; it is not reproduced here); 771.3.3.1 (maximum raised from 10 to 40 Ω, according to the foreword of 771, see ELEC-PRO-8). Clamp: ELEC-PAT-11.

### ELEC-MED-6: Test each RCD (*diferencial*) with a tester, not just with the button
- **Rule:** each RCD (*interruptor diferencial*) is tested with an RCD tester that complies with IEC 61557-6, injecting the current downstream (at a socket outlet or terminal of the circuit), in both polarities of the wave (0° and 180°). These are the five tests that the SRT Guide requires. Values for general-type (instantaneous) RCDs, with sinusoidal alternating current (valid for types AC, A, F and B):

  | Test | Test current | Required result |
  |---|---|---|
  | Non-operation | 0.5 × IΔn | Must not trip |
  | Ramp (increasing current) | From 0.5 to 1 × IΔn | Trips between 0.5 and 1 × IΔn (for 30 mA: between 15 and 30 mA), within 300 ms |
  | Time at IΔn | 1 × IΔn applied suddenly | ≤ 300 ms |
  | Time at 2 IΔn | 2 × IΔn applied suddenly (60 mA for a 30 mA RCD) | ≤ 150 ms |
  | Time at 5 IΔn | 5 × IΔn applied suddenly (150 mA for a 30 mA RCD) | ≤ 40 ms |

  For selective RCDs (type S, used as the incoming device upstream of the 30 mA ones) the times have a minimum and a maximum: at IΔn between 130 and 500 ms; at 2 IΔn between 60 and 200 ms; at 5 IΔn between 50 and 150 ms (see source).

  If you also test with other waveforms, the windows change (see source):

  | Test waveform | Types it applies to | Ramp tripping window | Currents for measuring time |
  |---|---|---|---|
  | Sinusoidal AC | AC, A, F, B | 0.5 to 1 × IΔn | 1, 2 and 5 × IΔn |
  | Pulsating DC (half wave, angle 0°) | A, F (and B) | 0.35 to 1.4 × IΔn | 1.4, 2.8 and 7 × IΔn |
  | Smooth DC | B | 0.5 to 2 × IΔn | 2, 4 and 10 × IΔn |

  For the SRT protocol the sinusoidal test is enough. If you test with pulsating DC, a type A RCD that trips at 38 mA (30 mA rated) is sound: don't judge it with the sinusoidal window.
- **Why:** the test button only shows that the mechanism moves; it does not measure at what current or how fast it trips, nor does it test the path through the PE. Res. SRT 900/2015 (item 32 of the protocol) requires verifying that the protection disconnects "dentro de los tiempos máximos" (within the maximum times) of AEA, and only a tester shows that. Homemade gadgets (plug with a resistor, lamp to earth) are inaccurate and dangerous.
- **How:**
  1. Prerequisite: PE continuity verified (ELEC-MED-3) and Ra measured (ELEC-MED-5).
  2. Disconnect the circuit's loads: their leakage currents add to the test current and make it trip early.
  3. Select on the tester IΔn, general or S, and the waveform. For the protocol, sinusoidal (AC) on any RCD type; pulsating or smooth waves are additional tests with their own window.
  4. Set the tester's touch voltage limit UL to 25 V (the selectable value closest to the regulatory 24 V; many come from the factory at 50 V) and compare the Ut it shows with 24 V. If it gives more than 24 V, stop and check PE and earth before continuing.
  5. Do: 0.5 IΔn (does not trip), 1 IΔn (time), 2 IΔn (time), 5 IΔn (time), ramp (tripping current). Each at 0° and 180°. Note the worst value.
  6. Caution: during the test, all exposed conductive parts connected to the same PE rise in potential, not only those of the circuit under test (in a building, all those on that earth). If the PE were broken upstream of the test point, the exposed parts of that section would be at phase voltage. Nobody should touch exposed conductive parts, metal appliances or pipes of that installation; in common services, warn the person in charge (*encargado*) beforehand.

  *Example:* RCD 2 × 40 A, 30 mA, type AC, sinusoidal test. Results: 0.5 IΔn no trip; ramp: 22 mA; 1 IΔn: 24 ms (0°) and 31 ms (180°); 2 IΔn: 15 ms and 18 ms; 5 IΔn: 12 ms. Complies (22 mA is between 15 and 30 mA; 31 ms ≤ 300 ms; 18 ms ≤ 150 ms; 12 ms ≤ 40 ms).
- **Verify:** schedule with IΔn, type, waveform used, tripping current, times at 1, 2 and 5 IΔn in both polarities, measured Ut. An RCD that in a sinusoidal test trips below 0.5 IΔn or does not trip at IΔn is replaced (not "adjusted").
- **Don't:** accept an RCD based on the test button; test with loads connected and record the "fast" trip as a merit; leave the tester at UL = 50 V; judge a pulsating DC test with the sinusoidal window; use a 300 mA RCD as socket-outlet protection (socket-outlet and lighting circuits up to 32 A use 30 mA).
- **Source:** Guía práctica SRT Res. 900/2015: "Los interruptores diferenciales de cualquier IΔn deben cumplir con los cinco ensayos" (RCDs of any IΔn must pass the five tests) (0.5 IΔn without tripping; ≤ 300 ms at IΔn; ≤ 150 ms at 2 IΔn; ≤ 40 ms at 5 IΔn; tripping between 0.5 and 1 IΔn with ramp, within 300 ms), instrument IEC 61557-6, citing AEA 90364 and IEC 61008; item 32 of the protocol. Test at 0° and 180° and criticism of the button and gadgets: Steck, "Disyuntor diferencial: seguridad y normativa" (RCD: safety and standards), *Ingeniería Eléctrica*, Dec 2017. **Not verified in a primary source:** the type S times; the windows with pulsating DC (IEC 61008-1 / 61009-1, 0.35 to 1.4 IΔn at 0°) and with smooth DC (IEC 62423, 0.5 to 2 IΔn), and their current multiples for times. They come from tester manuals and knowledge of the standard and were not re-verified in this session; Ed. 4.0 of IEC 61008-1 (2024) harmonized its tables with IEC 61009 and IEC 60755, so confirm them in the current text, in the tester manual or in the RCD's data sheet. Selectable UL 25/50 V: practice of IEC 61557-6 instruments.

### ELEC-MED-7: Polarity, phase switching and phase sequence
- **Rule:** verify that light switches (*llaves de luz*) switch the phase and not the neutral, that the phase reaches the terminal marked L (or phase) of socket outlets and appliances, that the center contact of screw lampholders is on the phase, and, in three-phase circuits, that the phase sequence is the intended one. The PIAs (MCBs) of single-phase circuits are two-pole (they switch phase and neutral): AEA prohibits single-pole, "1P+N" and unprotected-neutral devices in single-phase (ELEC-PRO-1). If you find single-pole PIAs in an existing installation, verify that they are on the phase and note it as an observation to correct.
- **Why:** with reversed polarity, a switched-off luminaire still has voltage at the lampholder, and whoever changes the lamp gets electrocuted "with the light off". A swapped phase sequence makes pumps, elevators and motors run backwards (in a building: water pumps and the common-services elevator).
- **How:**
  1. Dead (together with continuity, ELEC-MED-3): with the phase-PE jumper in place at the panel and the light switch closed, measure between the lampholder's center contact and the PE: it must give a low R1 + R2. With the switch open, it must read open. If it is the other way around, the switch is on the neutral.
  2. Live (confirmation, measurement without work): with a multimeter, phase-earth ≈ 220 V and neutral-earth ≈ 0 V at each socket outlet; with the light switch open, no voltage at the lampholder with respect to earth.
  3. Three-phase: phase sequence tester (IEC 61557-7) at the common services panel and at motor terminals before connecting loads.
  4. If something is reversed: switch off, apply lockout/tagout, correct, measure again. If the reversal comes from the service connection (*acometida*) or the meter, see ELEC-MED-21.
- **Verify:** schedule with "polaridad ok" (polarity ok) per circuit and "secuencia L1-L2-L3 ok" (sequence ok) on each three-phase panel; rotation test of pumps and elevator with no load or with the equipment technician.
- **Don't:** use the screwdriver voltage tester (non-contact voltage tester, *buscapolo*) as the only instrument (it may not indicate with a floating neutral or may give false positives); correct a reversal live; accept single-pole PIAs in a new installation.
- **Source:** polarity and phase order as tests of AEA 90364-6, 613.1, according to *Ingeniería Eléctrica* 305 (Dec 2015); polarity as a dead test: IEC 60364-6:2016, 6.4.3.6. Two-pole PIAs: AEA 90364-7-770 Ed. 2017, 770.16.5.1, and AEA 90364-7-771 Ed. 2006 (two-pole switching according to its foreword; see ELEC-PRO-1). Phase sequence testers: IEC 61557-7. **Not verified in a primary source:** the physical phase/neutral position in the IRAM 2071 socket outlet seen from the front; use the manufacturer's L/N marking.
### ELEC-MED-8: Voltage at socket outlets and measured voltage drop
- **Rule:** with the installation in service, measure the mains voltage at the main panel and the voltage drop of each final circuit with a known load, measuring at the same time (or in two consecutive readings, with the same load) at the PIA (MCB, *térmica*) output and at the farthest socket outlet. Compare that drop with the circuit's calculated drop, and the sum of drops from the origin with the total limit.
- **Why:** a drop higher than calculated indicates a loose terminal, a bad splice or a smaller cross-section than designed: it is heat concentrated at one point and a fire risk. A mains voltage out of tolerance is a complaint to the utility (*distribuidora*), not a problem of the installation. Measuring "no load vs. load" only at the socket outlet mixes the drop in the grid, the service connection (*acometida*) and the upstream lines with that of the circuit, and the grid also fluctuates between one reading and the next: it leads you to look for faults that do not exist.
- **How:**
  1. CAT III (or higher) multimeter on the AC range; ideally two, one at the panel and another at the socket outlet.
  2. Connect a known resistive load at the farthest socket outlet (e.g. an electric kettle or a heater of about 2 kW, about 9 A at 220 V).
  3. With the load connected, measure U at the PIA's output terminals (through the openings of the inner cover (dead front, *contratapa*), fine IP2X probes) and U at the socket outlet. Circuit drop: ΔU = U panel − U socket outlet; ΔU % = ΔU / 220 V × 100.
  4. Scale to the circuit's design current (the drop is proportional to the current) and compare with the calculation report.
  5. Alternative dead check: ΔU ≈ I × (R1 + Rn), with R1 + Rn taken from the measured continuity (if phase and neutral have the same cross-section and length as the PE, R1 + Rn ≈ R1 + R2).

  *Worked example:* 4th-floor socket-outlet circuit, 2.5 mm², 22 m, measured R1 + R2 = 0.35 Ω (ELEC-MED-3). With 9 A at the farthest socket outlet: PIA output 220.6 V, socket outlet 217.4 V → ΔU = 3.2 V → 3.2 / 220 × 100 = 1.45 % at 9 A. Expected: 0.35 Ω × 9 A = 3.15 V: it matches. At the design current, for example 10 A: 3.2 V × 10/9 = 3.6 V → 1.6 %, which is compared with the 1.6 % in the calculation report for that circuit. The total drop from the origin (sub-main + circuit) is compared with the 3 % in [conductors-and-conduits.md](conductors-and-conduits.md) (ELEC-CON-9). If with 9 A you measure 6.5 V on the circuit (0.72 Ω apparent, double what was expected), there is a bad terminal or splice: find it by measuring section by section or with thermography (ELEC-MED-23). Repeating the measurement at another time of day can give a different absolute voltage because the grid varies; the circuit drop, measured panel to socket outlet with the same load, should not change.
- **Verify:** mains voltage at the main panel within the supply tolerance (±8 % of 220 V, that is from 202 to 238 V, in the Edenor/Edesur area); circuit drop consistent with the calculated one (large differences are investigated).
- **Don't:** "fix" a high drop by increasing the PIA's rating; compare the no-load/load difference measured only at the socket outlet with the circuit's calculated drop; remove the inner cover live to measure (except trained personnel with PPE (*EPP*) and a procedure; measure through the openings of the inner cover, at the terminal screws of the modular devices, with fine IP2X probes).
- **Source:** voltage drop as a test of AEA 90364-6, 613.1, according to *Ingeniería Eléctrica* 305 (Dec 2015). Voltage tolerance in MV and LV in the Edenor/Edesur area: ±8 % of the nominal value (202.4 to 237.6 V at 220 V), Subanexo 4 "Normas de calidad del servicio público y sanciones" (public service quality standards and penalties) for the period 2025-2030, item 2 (Res. ENRE 304/2025 Edenor and 303/2025 Edesur; the same ±8 % as the RTI 2017-2021 period, item 2.2.1, with ±5 % in HV); same source as [troubleshooting-common-cases.md](troubleshooting-common-cases.md) and [protection.md](protection.md). **Not verified in a primary source:** the Edesur subannex (Res. 303/2025) re-read, and the tolerance in other provinces (it depends on each concession contract). Voltage drop limits of 771: see [conductors-and-conduits.md](conductors-and-conduits.md).

### ELEC-MED-9: Fault loop impedance when protection is by overcurrent (TN) or to bound Ra (TT)
- **Rule:** in TN-S (only with a dedicated transformer or a generator set), when protection against indirect contact is provided by a PIA or fuse and not by an RCD, measure or calculate the phase-PE loop impedance (Zs) at each exposed conductive part and verify that the fault current makes the protection trip within the maximum time that applies to that circuit. In TT, loop measurement serves as an alternative method to bound Ra (ELEC-MED-5); protection is provided by the RCD (*diferencial*).
- **Why:** in TN the fault current is high and the PIA disconnects it, but only if the loop is low enough. In TT the fault current is low (on the order of 5 to 20 A) and a PIA does not trip: that is why in TT the only valid protection against indirect contact is the RCD.
- **How:**
  1. Loop tester (IEC 61557-3) between phase and PE at the farthest exposed conductive part or socket outlet.
  2. Maximum disconnection times (Ut = 24 V, U0 = 220 V):

     | Circuit | System | Maximum time |
     |---|---|---|
     | Final lighting and socket-outlet circuits up to 32 A | Any | That of table 41.3 / 771.18.I (see table; much less than 1 s) |
     | Sub-mains and circuits not covered by that table | TN-S | 2 s; up to 5 s if selectivity requires it |
     | Sub-mains and circuits not covered by that table | TT | 1 s |

  3. Criterion by device: with a PIA (IEC 60898), fault current Ik = U0 / Zs greater than the maximum instantaneous tripping current: 5 × In (B curve), 10 × In (C curve), 20 × In (D curve); instantaneous tripping meets any time in the table. With IEC 60947-2 circuit breakers, Ik 20 % above the short-circuit setting. With fuses (IEC 60269), the fault current has to blow them, according to their curve (IEC 60269-2-1), within the time from the table above that applies to the circuit: that of table 771.18.I on final lighting and socket-outlet circuits ≤ 32 A, not 5 s.
  4. Temperature correction: the tester measures with the conductors cold, and in a fault they heat up and their resistance rises. Criterion: Zs measured at ambient temperature ≤ 2/3 × U0 / Ia.

  *Worked example (TN-S):* PIA C16, U0 = 220 V. Ia = 10 × 16 A = 160 A. Zs max = 220 V / 160 A = 1.375 Ω. Permissible cold measurement: 2/3 × 1.375 Ω = 0.92 Ω. You measure 0.9 Ω → it just complies (Ik = 220 / 0.9 = 244 A > 160 A, with margin for heating). You measure 1.3 Ω → it does not comply even though it is less than 1.375 Ω: change to a B curve (Ia = 80 A, Zs max = 2.75 Ω, cold 1.83 Ω), increase the cross-section or add an RCD.

  *Example (TT, why the RCD is needed):* Rb = 1 Ω, Ra = 10 Ω → Id = 220 / (1 + 10) = 20 A; the exposed conductive part is at 20 A × 10 Ω = 200 V. A B20 PIA needs 60 to 100 A to trip instantaneously: it does not trip.
- **Verify:** Zs recorded per circuit and compared with 2/3 × U0/Ia; in TT, Ut measured by the RCD tester ≤ 24 V.
- **Don't:** rely on the PIA as protection against indirect contact in TT; accept a fuse that takes 3 s on a socket-outlet circuit because "it is less than 5 s"; measure the phase-PE loop on a circuit with a 30 mA RCD with an instrument that has no "no-trip" mode.
- **Source:** Guía práctica SRT Res. 900/2015 (SRT practical guide): times of table 41.3 / 771.18.I for final lighting and socket-outlet circuits up to 32 A "cualquiera sea el ECT" (whatever the earthing system), and a) TN-S 2 s for sub-mains and circuits not covered, extendable to 5 s for selectivity, b) TT 1 s; criteria 5/10/20 × In and 20 % for IEC 60947-2; TT examples with Id ≈ 20 A and B20 from 60 to 100 A. The same guide, in the fuse bullet, says "en como máximo 5 segundos" (in at most 5 seconds): it contradicts its own table, which is what governs for final circuits ≤ 32 A. Times: AEA 90364-7-771, table 771.18.I (see table; not reproduced). 2/3 criterion: IEC 60364-6:2016, annex C (informative); the British guidance (BS 7671) uses a factor of 0.8 (1.10 Ω in the example), less conservative; this guide adopts the IEC one. **Not verified in a primary source:** the text of annex C (not re-consulted in this session).

### ELEC-MED-10: Earthing and exposed-part continuity protocol, Res. SRT 900/2015
- **Rule:** in every workplace (shop, office, workshop, and in practice also the common services of an owners' association (*consorcio*) with staff), the earthing measurement and the verification of continuity of exposed conductive parts are documented in the Res. SRT 900/2015 protocol, are valid for 12 months, and if they do not comply an action plan is drawn up.
- **Why:** it is mandatory under Ley 19.587 de Higiene y Seguridad en el Trabajo (occupational health and safety law); the ART (workers' compensation insurer) and the labor inspectorate ask for it, and after an electrical accident it is the first document anyone looks at. For the owner of a shop or office it is the proof that the installation protects their employees against indirect contact.
- **How:** the protocol has 41 items in three blocks:
  1. Establishment data (company name, address, CUIT tax ID), instrument (brand, model, serial number, **date of last calibration**), date and time of the measurement, method used. A **copy of the calibration certificate** issued by the laboratory and a **sketch** (*croquis*) with the numbered measurement points are attached.
  2. For each earth electrode: number (matches the sketch), sector, soil condition, use (system, protection of exposed parts, IT, lightning protection...), earthing system (item 26), value in Ω and whether it complies with the AEA regulation (items 27 and 28), whether the earth circuit is continuous and permanent, whether it has capacity for the fault current (item 30), what protection against indirect contact there is (RCD, circuit breaker, fuse) and whether it disconnects within the AEA times (item 32).
  3. Conclusions and recommendations.

  Signature: the documentation is signed by the professional involved with first name, last name and license (*matrícula*). Which degrees are authorized depends on the professional scope (*incumbencias*) and on the professional council (*consejo profesional*) of the jurisdiction (engineers, graduates in health and safety, technicians depending on the case); see [regulations-and-permits.md](regulations-and-permits.md).
- **Verify:** protocol signed less than 12 months ago; calibration certificate attached and valid at the date of the measurement; sketch with all points; all RCDs tested with a tester (item 32, the five tests of ELEC-MED-6); if something does not comply, an action plan with dates.
- **Don't:** fill in item 32 because you pressed the test button; reuse another year's protocol by changing the date; measure with an instrument without a calibration certificate.
- **Source:** Res. SRT 900/2015 (BO 2015-04-28): art. 1 (protocol mandatory in the workplace), art. 2 (validity 12 months), art. 3 (action plan), art. 4 (periodic check of the protective devices), art. 5 (practical guide on the SRT website). Annex and instructions with 41 items (argentina.gob.ar, `res_srt_900_15-anexo.pdf`). Items 26, 27, 28, 30 and 32: SRT practical guide, which cites them by number. Signature: Res. CPIQ 4/2025 (BO 2025-11-25), recitals: the documentation of Res. SRT 900/2015 must be signed by the professional involved with name and registration. That resolution repealed Res. CPIQ 2/2017 and regulates the RUPAT (Registro Unificado de Profesionales para mediciones de Puesta a Tierra, unified register of professionals for earthing measurements) for the licensees of that council (Ingeniería Química, chemical engineering); other councils (e.g. electrical engineering) have their own rules. **Not verified in a primary source:** the numbers of the other fields in the instructions (the official annex is an image; that is why they are cited by name here); that Res. 900/2015 expressly covers condominium buildings' owners' associations (*consorcios de propiedad horizontal*) (it applies to every workplace; an owners' association with a building manager (*encargado*) is one).

### ELEC-MED-11: Job handover documentation
- **Rule:** an installation is handed over with its complete file; without the file, the job is not finished.
- **Why:** the next electrician, the owners' association, the ART or the utility need to know what is there, how it was calculated and how it was tested. Without drawings, any extension is done blind.
- **How:** the file (paper and PDF) contains:

  | Document | Minimum content | Who issues it |
  |---|---|---|
  | As-built drawings | Outlet points (*bocas*), conduits, boxes, panels, actual routes (not the design ones) | Designer / installer |
  | Single-line diagram (*unifilar*) of each panel | Protective devices (rating, curve, breaking capacity, IΔn, type), cross-sections, identified circuits; a copy inside the panel | Designer / installer |
  | Calculation report | Electrification grade and demand, cross-sections, voltage drop, short-circuit current, coordination, earthing (see [grades-and-circuits.md](grades-and-circuits.md), [protection.md](protection.md)) | Professional |
  | Initial test report | Schedule (*planilla*) of ELEC-MED-1 to 9, 17, 18, 22 and 23 with values, instrument and calibration date, signature | Whoever measured |
  | SRT 900/2015 protocol | If it is a workplace (ELEC-MED-10) | Authorized professional |
  | DCI / installation certificate | In the Edenor and Edesur area, Declaración de Conformidad de la Instalación (DCI, installation conformity declaration) (Res. ENRE 225/2011 and form Res. ENRE 269/2012) to connect the supply; in other provinces, the certificate required by the utility or the local professional council/body | Licensed / qualified electrician (see [regulations-and-permits.md](regulations-and-permits.md)) |
  | Material certificates | Electrical safety mark of PIAs, RCDs, socket outlets, cables; data sheets | Manufacturers |
  | Warranty | Scope and term for the labor; manufacturer warranties | Installer |
  | Instructions for use | See ELEC-MED-15 | Installer |

- **Verify:** the client or the owners' association signs receipt of the file; the panel's single-line diagram matches what is installed (open the panel and count).
- **Don't:** hand over the design drawings as "as-built"; leave the panel without the circuits identified.
- **Source:** documentation and diagrams as part of the inspection of AEA 90364-6, 612.2 (*Ingeniería Eléctrica* 305, Dec 2015). DCI: Res. ENRE 225/2011 (Reglamento para la Conexión de Nuevos Suministros, regulation for connecting new supplies, T1R of Edenor and Edesur) and Res. ENRE 269/2012 (DCI form), according to argentina.gob.ar ("Nuevos suministros domiciliarios", new residential supplies) and Boletín Oficial notices. The material certification regime is in [regulations-and-permits.md](regulations-and-permits.md).

### ELEC-MED-12: Staged commissioning
- **Rule:** energize one level at a time, from upstream to downstream, with everything below open, measuring at each step before closing the next one.
- **Why:** if there is a fault, it trips in a small, known section; energizing everything together turns a fault into a blackout and a blind search, and exposes whoever operates the switchgear to an arc at the main panel.
- **How:** checklist (4-story building with single-phase supplies per unit and common services; adapt it):
  1. Dead tests complete and recorded (ELEC-MED-1 to 5). Test jumpers removed. SPDs (*DPS*) reconnected. Tools and debris out of the panels. Inner covers in place.
  2. All switches open: incoming switches, sub-mains, RCDs and PIAs of all panels.
  3. The connection of the meter and the service connection is done by the utility. Never tamper with the meter, its seals or the utility's terminals (see [buildings.md](buildings.md)).
  4. With the supply connected: measure at the input terminals of each main panel (with the inner cover on, CAT IV instrument): phase-neutral ≈ 220 V, phase-earth ≈ 220 V, neutral-earth ≈ 0 V (a few volts is normal in TT; if it gives tens of volts, broken or badly connected neutral: don't continue). If the terminal marked "N" gives 220 V to earth and the "L" one almost 0 V, phase and neutral come reversed from the service connection or the meter (ELEC-MED-21).
  5. Close the main panel's incoming switch. Measure at the output.
  6. Close the sub-mains one at a time (in a building: common services first, then each unit, floor by floor). Measure at the input of each sub-panel (TS, *tablero seccional*).
  7. At each sub-panel: close the RCD with all PIAs open. If it trips like this, the fault is between the RCD and the PIAs (busbar comb (*peine*), jumpers, a terminal touching the earth bar), or the RCD is defective or wrongly wired (e.g. neutral taken from upstream of the RCD): open, apply lockout/tagout (LOTO, *consignación*) and inspect (see ELEC-DIA-8 and ELEC-DIA-9 in [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
  8. Close the PIAs one at a time. If an RCD trips when closing a circuit with no load, that circuit has an earth fault. If it trips only when there is load on a circuit (or on another one protected by another RCD), suspect a shared or crossed neutral between circuits of different RCDs (ELEC-DIA-5).
  9. Live tests: polarity (ELEC-MED-7), loop and prospective short-circuit current (ELEC-MED-9 and 17), RCDs with a tester (ELEC-MED-6), voltage and drop (ELEC-MED-8), leakage (ELEC-MED-18).
  10. Functional tests: each light switch, each socket outlet (with a socket tester or an appliance), emergency lights and SPDs (ELEC-MED-22), pumps (sequence and rotation), door entry system, elevator with its technician. If an RCD trips only at this point, with the real loads, go back to step 8 (crossed neutrals) and to ELEC-MED-18 (accumulated leakage).
  11. Loads little by little. After a few hours with a representative load: thermography of the panels (ELEC-MED-23) or, if there is nobody to do it safely, switch off, apply lockout/tagout and retighten the terminals to the manufacturer's torque. Measure each circuit's current with a clamp meter and compare it with its PIA.
  12. Complete and sign the schedule, close the file (ELEC-MED-11), explain ELEC-MED-15 to the user.
- **Verify:** each step has its reading recorded; no trip was left "unexplained".
- **Don't:** close everything at once; bypass (jumper) an RCD that trips "to be able to continue"; energize with the panel's inner cover removed; touch terminals "to see if they are getting hot".
- **Source:** initial verification practice of AEA 90364-6 (inspection and tests before commissioning, 612/613 according to *Ingeniería Eléctrica* 305). **Not verified in a primary source:** the detailed step-by-step sequence, which is good site practice and not a literal AEA clause.
### ELEC-MED-13: Instruments: measurement category, standards and calibration
- **Rule:** use instruments with the measurement category (CAT) suited to the point where you measure, that meet the relevant part of IEC 61557 for each test, and with a current calibration certificate issued by a laboratory.
- **Why:** the closer to the origin of the installation, the larger the transients (switching and lightning surges) and the energy available in a short circuit; a low-category instrument can explode in your hand. And a measurement taken with an uncalibrated instrument is not valid in an SRT protocol.
- **How:**

  | Category (IEC 61010-1) | Where | Example in a building |
  |---|---|---|
  | CAT IV | Origin of the installation: service drop (*acometida*), meter pillar (*pilar*), meters, main panel incoming | Incoming terminals of the main panel or of the common services panel |
  | CAT III | Fixed distribution inside the building: panels (distribution boards, *tableros*), sub-mains (feeders), fixed equipment, motors | Sub-panels (TS, *tablero seccional*) of each unit, pump panel |
  | CAT II | Loads plugged into socket outlets (*tomas*): household appliances, tools | Measuring at a socket outlet |

  - A high-category instrument can be used to measure at a lower category, never the other way round.
  - Within the same category, the higher the rated voltage, the higher the impulse withstand (CAT III 600 V: 6 kV; CAT III 1000 V: 8 kV). Across categories, the category weighs more: a CAT III 600 V instrument is safer than a CAT II 1000 V one even though both are tested with a 6 kV impulse, because the CAT III test uses a lower-impedance source (2 Ω versus 12 Ω), that is, more energy.
  - For site work, a multimeter and test leads rated CAT IV 600 V / CAT III 1000 V cover every point. Probes and leads also have a category: the lowest in the set is what counts.
  - Distrust self-declared categories: look for the mark of an independent testing laboratory.
  - Standards per test: IEC 61557-2 (insulation), -3 (loop impedance and prospective short-circuit current), -4 (continuity), -5 (earth resistance), -6 (RCDs, *diferenciales*), -7 (phase sequence), -10 (combined instruments).
  - Calibration: the SRT protocol asks for the date of the last calibration and a copy of the laboratory certificate. The interval is set by the instrument manufacturer or by the quality plan of whoever measures; in practice, every 12 months. Before each working day: a quick check (probes shorted together for continuity, measure a known voltage, test the instrument on a resistor of known value).
- **Verify:** calibration label with date; certificate on file; category and voltage of the instrument and of the leads equal to or higher than those of the measuring point; leads without cuts and with finger guards.
- **Don't:** measure in the main panel with a CAT II multimeter; use leads with damaged insulation or without caps; lend the RCD tester (*probador de ID*) without its certificate if a protocol will later be signed with it.
- **Source:** categories and impulses: IEC 61010-1, as explained by Fluke ("Clasificaciones de categoría IEC" (IEC category ratings), with the transient table: CAT II 1000 V and CAT III 600 V, 6 kV, 12 Ω and 2 Ω sources; and "Aspectos básicos sobre seguridad eléctrica" (electrical safety basics)). Instrument standards: IEC 61557 series, cited by the Guía práctica SRT (SRT practical guide) (61557-4 and -6) and by *Ingeniería Eléctrica* 305. Calibration: instructions of Res. SRT 900/2015 (instrument fields, date of last calibration and certificate). **Not verified in a primary source:** the impulse values (8 kV for CAT III 1000 V) were not re-verified in this session; a mandatory calibration interval (Res. 900/2015 does not set a period; the 12 months are common practice and a usual manufacturer recommendation).

### ELEC-MED-14: Dead tests under lockout/tagout; live tests only by trained personnel
- **Rule:** before a dead test, apply lockout/tagout (LOTO, *consignación*): visible isolation, lock and tag, verify absence of voltage with a tester proven before and after, and signage. Live tests are done only by trained personnel, with a suitable CAT instrument, without opening terminals and with PPE (*EPP*): class 00 or 0 dielectric gloves (IEC 60903 / IRAM 3604) in good condition and checked by inflation, face shield or arc-rated glasses, cotton or flame-resistant clothing (not synthetic) and dielectric footwear. At the main panel incoming (CAT IV, high short-circuit energy) face protection is not optional.
- **Why:** the megohmmeter (megger) puts 500 V DC on conductors that another person may be touching, and leaves stored charge on long cables; the RCD tester puts voltage on exposed conductive parts. An installation that has been "switched off" can have backfeeds (another panel, a generator set, a UPS). And an arc at the origin of the installation burns the face and melts synthetic clothing onto the skin. An ordinary work glove does not insulate.
- **How:** full procedure and glove classes in [site-safety.md](site-safety.md) (ELEC-SEG-10 and 11). In a building: notify neighbors/the person in charge before insulation testing or RCD testing in common services (pumps and elevator are left without supply, or with exposed conductive parts that can rise in voltage during the test).
- **Verify:** padlock and tag in place; record of who locked out and who released; gloves with a test date and no damage.
- **Don't:** trust "I already switched off the MCB (*térmica*)"; insulation-test with people working on the same circuit; touch conductors right after the insulation measurement ends without waiting for the discharge; measure in the main panel with split-leather or cleaning gloves.
- **Source:** Decreto 351/79, Anexo VI (chapter 14, electricity) and Decreto 911/96 (construction; art. 86, insulating gloves for handling LV cables), Ley 19.587, which refer to the AEA regulations (Guía práctica SRT Res. 900/2015). Gloves: IEC 60903 (class 00 up to 500 V AC and class 0 up to 1000 V AC), with IRAM 3604 as the equivalent according to manufacturers (see ELEC-SEG-10). Operational detail in [site-safety.md](site-safety.md).

### ELEC-MED-15: Instructions to the user: test the RCD (*ID*) once a month
- **Rule:** at handover, recommend to the user (and leave it in writing, and stuck on the inner cover (dead front, *contratapa*) of the panel) that they press the test button of each RCD (*diferencial*) once a month and that it must trip; if it does not trip, call an electrician. This is a recommendation of the SRT Guide and of manufacturers, not a regulatory obligation for dwellings. In workplaces, art. 4 of Res. SRT 900/2015 requires a periodic check of the devices (no period set) and the protocol is renewed every 12 months.
- **Why:** the mechanism of an RCD that is never operated can seize; the monthly test checks the mechanical operation. It does not replace the test with a tester (ELEC-MED-6).
- **How:** the instruction sheet includes: what each switch does (simplified single-line diagram); test the RCD monthly; what to do if it trips (unplug everything, reset, plug in one at a time: the one that makes it trip has the fault); do not reset more than twice in a row if it trips immediately; do not add socket outlets or use triple adapters, adapters or daisy-chained power strips (*zapatillas*); do not change the rating of the MCBs; recommend a periodic inspection by a professional (ELEC-MED-19); the utility's (distribution company, *distribuidora*) emergency phone number (no personal data in this guide).
- **Verify:** label "Probar mensualmente" (test monthly) on the panel; sheet signed by the user.
- **Don't:** tell the user "si salta mucho, sacalo" (if it trips a lot, take it out); leave the RCD covered or inaccessible.
- **Source:** Guía práctica SRT Res. 900/2015, on art. 4: "Se aconseja la prueba con frecuencia mensual de los dispositivos, para verificar su funcionamiento mecánico" (monthly testing of the devices is advised, to verify their mechanical operation); Res. SRT 900/2015, art. 4 ("se debe controlar periódicamente" (must be checked periodically), no interval) and art. 2 (12-month validity). Monthly interval in manufacturer instructions: see ELEC-PRO-13. Triple adapters and adapters: IRAM, "Triples y adaptadores inseguros" (unsafe triple adapters and adapters), *Ingeniería Eléctrica* 347.

### ELEC-MED-16: A bad result is investigated, not dressed up
- **Rule:** if a value fails or is odd compared with the others (insulation much lower than on similar circuits, high continuity, an RCD that trips at 8 mA in a sinusoidal test), find the cause, correct it and measure again. Record the real value in the protocol; if it cannot be corrected right away, it goes into the action plan with a date.
- **Why:** the number exists to find the defect; tampering with the number leaves the defect. After an accident, a false protocol aggravates the liability of whoever signed it.
- **How:** see the fault-finding guide in [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (low insulation from moisture in boxes, neutrals crossed between circuits on different RCDs, loose terminals, corroded earth rod (*jabalina*)).
- **Verify:** every "no cumple" (fails) in the schedule (*planilla*) has an action and a re-measurement, or an entry in the action plan.
- **Don't:** repeat the earth measurement after wetting the earth rod so that it "passes"; pick whichever polarity value suits you; replace a 30 mA RCD with a 300 mA one because it "trips a lot".
- **Source:** Res. SRT 900/2015, art. 3 (action plan in case of non-compliance). AEA 770.19.5.2.1 (Corrigendum 1, 2018): evident differences between circuits require investigation.

### ELEC-MED-17: Prospective short-circuit current at each panel and breaking capacity
- **Rule:** with the installation energized, measure the phase-neutral prospective short-circuit current (PSC/PFC) at the incoming terminals of each panel with an L-N loop tester, and verify that the breaking capacity of the incoming device and of each MCB (PIA) is greater than or equal to the larger of two figures: the Icc reported by the utility (or the one calculated in the design report) and the measured one.
- **Why:** an MCB that interrupts fewer kA than the fault may fail to extinguish the arc, weld or explode, and no other test detects it. It is a frequent error in panels near the meter or a transformer (meter cabinet of a building). The measurement confirms the calculation, but gives the Icc at that moment: if the utility changes or upsizes the transformer, it rises; that is why it is also compared with the utility's figure.
- **How:**
  1. Loop tester (IEC 61557-3), L-N mode. No current flows to earth between phase and neutral, so it does not trip the RCD.
  2. The instrument calculates Icc = U0 / Z(L-N). In three-phase systems the phase-to-phase Icc is higher than the L-N one: use the instrument's three-phase mode or the calculator.
  3. Record the Icc per panel and compare it with the breaking capacity on the single-line diagram (ELEC-PRO-3).

  *Worked example:* main panel of a unit in the meter cabinet: measured Z(L-N) = 0.05 Ω → Icc = 220 V / 0.05 Ω = 4,400 A. A 4.5 kA MCB is just enough, and if the utility reports 6 kA, ≥ 6 kA is needed. In the sub-panel on the 4th floor: Z(L-N) = 0.16 Ω → Icc = 220 / 0.16 = 1,375 A: a 3 kA MCB is enough, and a 4.5 kA one gives margin.
- **Verify:** every device on the single-line diagram with breaking capacity ≥ the maximum Icc of its panel; measured Icc recorded in the schedule.
- **Don't:** accept a 3 kA MCB in the meter cabinet without data; use only the measured Icc if the utility reports a higher one; rely on cascading (back-up protection) with the upstream device without the manufacturer's table.
- **Source:** rule of breaking capacity ≥ prospective Icc and utility figure: AEA 90364-7-770 Ed. 2017, 770.15.2.2.2 (see ELEC-PRO-3). Measurement of loop impedance and prospective current: IEC 61557-3. **Not verified in a primary source:** that AEA 90364-6 Ed. 2025 lists prospective Icc measurement as a test; in this guide it is good practice to confirm the calculation.

### ELEC-MED-18: Leakage current with a leakage clamp meter
- **Rule:** before fitting a new RCD in an existing installation, when handing over a job with a lot of electronic equipment, and whenever there are trips with no clear cause, measure with a leakage clamp meter (*pinza de fugas*) the residual current of each circuit and the total per RCD, with the usual loads running. The total standing leakage on one RCD should not exceed about 30 % of its IΔn (≈ 9 mA for 30 mA).
- **Why:** every class I appliance with a filter leaks some current to earth by design. Added together, plus some moisture, they reach the RCD's threshold and cause trips "for no reason"; the user ends up removing the RCD. The clamp shows how much leakage there is and where, without switching anything off.
- **How:**
  1. Leakage clamp meter (mA clamp with a resolution of 0.01 mA or better), CAT III. Live measurement: trained personnel only, without touching terminals, clamping cables through the inner cover or in an accessible box without opening connections.
  2. Clamp the circuit's phase and neutral together (not the PE): the clamp measures the difference, which is the circuit's leakage. Do it at the output of each MCB and, if possible, at the input of each RCD.
  3. Another option: clamp only the PE of the circuit or of the panel, to see the leakage returning through earth.
  4. Indicative values: portable or heating class I appliances, on the order of 0.75 mA; fixed or IT equipment, up to about 3.5 mA. An empty circuit (no loads) should read almost 0.
  5. If the total per RCD approaches 9 mA (30 mA RCD), split the circuits among more RCDs (ELEC-PRO-11). If a circuit without loads shows leakage, insulation-test that circuit (ELEC-DIA-4).
- **Verify:** leakage per RCD recorded with the loads present at the time of measurement; no RCD with standing leakage close to 0.3 IΔn.
- **Don't:** clamp phase, neutral and PE together (it reads almost zero even if there is leakage); believe the clamp sees transient leakage (inrush peaks, storms): it measures only the standing leakage.
- **Source:** limit of ~0.3 IΔn: IEC 60364-5-53 (accumulation of protective conductor currents), according to ELEC-PRO-11; measurement with a leakage clamp meter: ELEC-DIA-6. **Not verified in a primary source:** the exact IEC subclause number and its AEA equivalent; the leakage values per appliance are product-standard limits (IEC 60335-1, IEC 62368-1) quoted from memory.

### ELEC-MED-19: Periodic inspection of existing installations and common services
- **Rule:** recommend to the owner or the owners' association (*consorcio*) a periodic inspection by a qualified professional, at the interval of ELEC-NOR-17 (dwelling every 5 years; offices, shops and common areas of condominium buildings (*propiedad horizontal*, PH) every 3; places of public assembly every 2; fire or explosion risk, every year). Where there are workers (including an owners' association with a person in charge (*encargado*, building caretaker)), the SRT 900/2015 protocol every 12 months as well.
- **Why:** installations deteriorate: terminals that loosen, RCDs that seize, earth rods that corrode, DIY extensions. Common services in a building have pumps, an elevator and emergency lighting that everyone uses, and nobody looks at the panel until it fails.
- **How:** the periodic inspection repeats the essentials of the initial one, adapted to an installation that cannot be fully dismantled:
  1. Visual inspection (ELEC-MED-2): damage, overheating, undocumented extensions, missing covers, single-line diagram up to date.
  2. Continuity of the PE and equipotential bonding (ELEC-MED-3), including the sub-mains in buildings.
  3. Insulation per circuit where it can be disconnected (ELEC-MED-4); otherwise, leakage measurement with a clamp (ELEC-MED-18).
  4. Ra with its soil condition (ELEC-MED-5) and comparison with previous measurements.
  5. All RCDs with a tester (ELEC-MED-6).
  6. Thermography under load (ELEC-MED-23) and re-tightening under lockout/tagout where needed.
  7. Common services: in addition, emergency lights with an autonomy test (ELEC-MED-22), SPDs (*DPS*), pump sequence and protection.
  8. Report with what was measured, what could not be measured and a prioritized correction plan.
- **Verify:** dated and signed report; measurements comparable with previous ones (same method and same points on the sketch (*croquis*)).
- **Don't:** replace the periodic inspection with the SRT protocol (the protocol looks at earth, continuity and disconnection, not insulation or the condition of the terminals); leave the common services panel out of the inspection "because it belongs to the owners' association".
- **Source:** intervals: Reglamento ENRE de conexión (ENRE connection regulations) (Res. ENRE 225/2011, 2022 edition text), section II point 5 and section III point 5, according to ELEC-NOR-17; annual protocol: Res. SRT 900/2015, art. 2. Principle of IEC 60364-6:2016, 6.5: the frequency is set according to the type of installation, its use, maintenance and external influences. **Not verified in a primary source:** whether AEA 90364-6 Ed. 2025 sets intervals or leaves them to the designer (its text was not consulted); municipal requirements for periodic electrical inspection for owners' associations (no general obligation was found; check with the municipality).
### ELEC-MED-20: Extension or alteration connected to an existing installation
- **Rule:** the new part is verified completely, as an initial installation (ELEC-MED-1 to 9). In addition, verify the existing parts its safety depends on: the PE and the earthing it connects to, the RCD (*disyuntor* / *diferencial*) that protects it, the incoming device and the MCB (*térmica*, PIA) and the cross-section of the circuit or line that feeds it. Whatever was not verified in the existing installation is recorded in writing.
- **Why:** a new circuit with an impeccable PE connected to an earth bar that does not reach any earth rod (*jabalina*) protects nobody. And a new circuit added to an old panel (distribution board, *tablero*) without an RCD, or hung off a 25 A MCB with 1.5 mm² cable, inherits the risk of the old installation.
- **How:**
  1. Inspection of the existing installation upstream: incoming device, RCD (or lack of RCD), MCB and cross-section of what feeds the extension, earth bar, earth rod.
  2. Continuity from the new exposed conductive parts to the earth rod, not only to the panel's bar.
  3. Measured Ra (ELEC-MED-5). If there is no PE and no earth rod: the extension carries its PE to a new, measured earth electrode, and extending the PE and the RCD to the rest is recommended (order of priorities in ELEC-DIA-17).
  4. Test with a tester of the RCD protecting the new circuits; if there is no RCD, a 30 mA one is installed before energizing the new part, and before that, measure the leakage (ELEC-MED-18) and the insulation of the existing circuits that will end up downstream of it.
  5. Insulation of the new circuits separately from the old ones.
  6. Update the single-line diagram (*unifilar*) and drawings; if the utility (distribution company, *distribuidora*) or the jurisdiction requires it, a new DCI (installation conformity declaration) or certificate.
- **Verify:** schedule (*planilla*) with the tests of the new part, the existing parts verified and a list of "no verificado / a corregir" (not verified / to correct).
- **Don't:** connect new three-pin socket outlets (*tomas*) to an installation without a PE; join the earth terminal to the neutral; sign as "instalación verificada" (installation verified) when only the extension was measured.
- **Source:** verification of extensions and alterations as an initial verification of the new part, with a check that it does not impair the safety of the existing installation: IEC 60364-6:2016, 6.4.1 (principle adopted in Part 6 of the AEA). **Not verified in a primary source:** the equivalent wording in AEA 90364-6 Ed. 2025.

### ELEC-MED-21: Phase and neutral reversed at the service connection, and neutral with voltage to earth
- **Rule:** at first energization and at every inspection, measure phase-neutral, phase-earth and neutral-earth at the main panel incoming. If phase and neutral arrive reversed from the service connection (*acometida*) or the meter, it is a complaint to the utility: it is not corrected by touching the meter or its terminals. If the neutral has tens of volts to earth, do not continue energizing until the cause is found.
- **Why:** with two-pole MCBs the installation still disconnects both conductors, but downstream the polarity is reversed everywhere (lamps live while switched off, appliance switches in the neutral). A few volts between neutral and earth are normal in a TT system (current in the network neutral). Tens of volts indicate a degraded or broken neutral at the service connection or in the building's common neutral, the prelude to an overvoltage that burns out appliances in several apartments (*deptos*).
- **How:**
  1. CAT IV, with the inner cover (dead front, *contratapa*) on, PPE (ELEC-MED-14). At the incoming terminals: L-N ≈ 220 V, L-PE ≈ 220 V, N-PE from 0 to a few volts.
  2. If the "N" terminal reads ≈ 220 V to earth and the "L" ≈ 0 V: reversal upstream. Leave everything open and ask the utility to correct it.
  3. If N-PE reads tens of volts: measure with and without the unit's own load, and in other units. If it rises across the whole building when one phase is loaded, suspect the common neutral (ELEC-EDI-11, ELEC-DIA-14) and notify the utility and the owners' association (*consorcio*). If it is only in one unit, check the neutral of its sub-main (feeder) (under lockout/tagout).
- **Verify:** L-N, L-PE and N-PE values recorded in the schedule of each main panel; complaint with a reference number if there was a reversal.
- **Don't:** "fix" the reversal by crossing cables in the main panel without the utility correcting the service connection (the next network intervention changes it back); join neutral and earth to "lower" the N-PE voltage; energize with tens of volts on the neutral.
- **Source:** TT system and separation of neutral and PE: Guía práctica SRT (SRT practical guide) Res. 900/2015. Phase-neutral reversal possible in the network, meter or socket outlet, as the reason for two-pole disconnection: ELEC-PRO-1. Broken neutral in buildings: ELEC-EDI-11 and ELEC-DIA-14. **Not verified in a primary source:** a regulatory N-PE voltage threshold; "a few volts" and "tens of volts" are a practical criterion.

### ELEC-MED-22: Emergency lights and SPDs (*DPS*) at commissioning
- **Rule:** before handover, test each emergency lighting unit by cutting its supply (it must light up instantly) and do the autonomy test (≥ 1.5 h on escape routes in dwellings). Verify that each SPD is reconnected after insulation testing, with its indicator showing "ok" and with its back-up protection.
- **Why:** an emergency light with an uncharged or badly connected battery is discovered on the day of the outage or the fire. An SPD left disconnected after insulation testing, or with a spent cartridge, protects nothing, and nobody finds out.
- **How:**
  1. Emergency lighting: leave the units charging for the time stated by the manufacturer (usually 24 h) before the autonomy test. Cut the circuit that feeds them and time with a watch until they go out or drop below the useful level. Also check that they recharge.
  2. Verify that the circuit of the self-contained units does not have a switch accessible to the public (ELEC-EDI-16).
  3. SPD: green indicator (or the manufacturer's indicator), short leads, back-up protection fitted (ELEC-PRO-18). If it has a signaling contact, test it.
- **Verify:** schedule with each emergency unit, measured autonomy time and date; SPDs with status and date of the check.
- **Don't:** accept the emergency lighting because "el led de carga está prendido" (the charging LED is on); leave the SPD removed after insulation testing; replace the emergency lighting with the generator set.
- **Source:** minimum autonomy 1.5 h (3 h where re-entry is needed) and illuminance of 1 lx: IRAM-AADL J 2027, according to ELEC-EDI-16. SPDs: ELEC-PRO-16 to 18. **Not verified in a primary source:** the charging time before the autonomy test (depends on the manufacturer; 24 h is usual in datasheets).

### ELEC-MED-23: Thermography of panels under load
- **Rule:** after a few hours under representative load, and at every periodic inspection, do thermography of the panels: main, sub-panels and common services. It is done by trained personnel, with a thermal imaging camera and PPE, without touching anything. If there is nobody who can do it safely, switch off, apply lockout/tagout and re-tighten the terminals to the manufacturer's torque.
- **Why:** a loose terminal heats up long before it burns, and poor contact is the fault that causes the most fires (ELEC-DIA-11). Infrared does not go through the inner cover or the door: a thermometer pointed at the front measures the plastic, not the terminal.
- **How:**
  1. Representative load: as a practical reference, more than 40 % of the circuit's rated load. With little load nothing shows up.
  2. To see the terminals you have to remove the inner cover while live: only trained personnel do it, with arc-rated face protection, dielectric gloves and non-synthetic clothing, keeping their distance and without inserting tools (ELEC-MED-14). If the panel has an inner cover with viewing windows or IR windows, even better.
  3. Adjust the emissivity: measure on the cable insulation or the device body (plastic, high emissivity), not on shiny metal, which reflects and gives false readings.
  4. Compare phases and identical devices with similar load, and also record each circuit's current (clamp meter) and the ambient temperature.
  5. Indicative criterion for temperature differences (ΔT):

     | ΔT between identical components with similar load | ΔT over ambient | Action |
     |---|---|---|
     | 1 to 3 °C | 1 to 10 °C | Possible deficiency: check at the next inspection |
     | 4 to 15 °C | 11 to 20 °C | Probable deficiency: repair at the next scheduled shutdown |
     | — | 21 to 40 °C | Deficiency: repair as soon as possible |
     | > 15 °C | > 40 °C | Serious: repair now (switch off if needed) |

- **Verify:** report with a thermal and a visible image of each hot spot, load at the time of measurement, ΔT and action; re-measurement after repair.
- **Don't:** "measure" temperature by resting your hand on the inner cover or by pointing the thermometer at the front of the panel; open the inner cover while live without PPE or training; re-tighten terminals while live.
- **Source:** predictive maintenance practice. **Not verified in a primary source:** the ΔT table comes from the thermographic inspection table of ANSI/NETA MTS (quoted from memory, not consulted in this session), and the 40 % minimum load is a common practical reference. There is no Argentine thermography standard that sets these values.

## Test record: 4-story building case
Building with ground floor and 4 floors, single-phase 220 V supplies per unit (TT), three-phase common services panel
(pumps, common lighting, door entry system, elevator if any). One schedule per panel. The values below are **an example of how to
fill it in**, not reference values.

**Header:** panel (e.g. "TS Depto 4.º B" (sub-panel, apartment 4th B)), date, who measures, instruments (brand, model, serial no., calibration
date), earthing system (TT), soil condition, ambient temperature.

| Circuit | Protection | Cross-section (mm²) | R1+R2 continuity (Ω) | Insulation L-N (MΩ) at 500 V | Insulation L+N to PE (MΩ) at 500 V | Polarity | RCD: IΔn / type (test waveform) | Ramp trip (mA) | t at IΔn (ms) 0°/180° | t at 2 IΔn (ms) 0°/180° | t at 5 IΔn (ms) | Ut (V) | Leakage (mA) | Remarks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IUG 1 (lighting) | PIA 2×10 A C | 1.5 | 0.42 | > 200 | > 200 | ok | 30 mA / AC (sinusoidal) | 21 | 25 / 28 | 14 / 16 | 11 | 0.4 | 0.3 | |
| TUG 1 (socket outlets) | PIA 2×16 A C | 2.5 | 0.35 | > 200 | 180 | ok | 30 mA / AC (sinusoidal) | 21 | 25 / 28 | 14 / 16 | 11 | 0.4 | 1.6 | Same RCD as IUG 1: RCD leakage 1.9 mA |
| TUE 1 (air cond.) | PIA 2×20 A C | 4 | 0.18 | > 200 | > 200 | ok | 30 mA / A (sinusoidal) | 23 | 22 / 30 | 15 / 19 | 12 | 0.4 | 1.1 | Appliance disconnected during insulation test |

**Sub-main and earth:** PE of the sub-main (sub-panel earth bar to main earth bar): 0.06 Ω,
expected 0.048 Ω (10 mm², 25 m) → ok. Earth electrode no. 1 (per sketch), use: protection of exposed conductive parts, method: earth resistance tester,
fall-of-potential, Ra = 6.8 Ω, maximum in table 771.3.I for IΔn ≤ 300 mA: 40 Ω → passes. Main equipotential bonding
(water, gas, structure): 0.05 to 0.08 Ω → ok. Supplementary equipotential bonding in the bathroom (pipes and floor grate to PE): 0.10 Ω → ok.

**Voltages and Icc:** main panel (TP) incoming 223 V L-N, 223 V L-PE, 0.8 V N-PE (service connection polarity correct). Icc L-N at the sub-panel
1,375 A, 4.5 kA MCB → ok. Voltage drop TUG 1 at 9 A: MCB output 221.0 V, farthest socket outlet 217.9 V → 3.1 V (1.4 %);
expected 0.35 Ω × 9 A = 3.2 V → ok.

**Commissioning:** SPD reconnected, indicator ok. Thermography under load: no hot spots (max. ΔT between poles 2 °C).

**Conclusion and signature:** passes / fails, pending actions, name, license (*matrícula*) and signature.

## What could not be verified in this edition
During the review of this document the web search budget ran out. For that reason the following remain marked as
**Not verified in a primary source**, and should be confirmed before citing them as mandatory: the text of Corrigendum 1 of the 770 in
the extra-low voltage row, the voltage tolerance of the current tariff review, the text of IEC 61008-1:2024
(type S, windows with pulsating DC), IEC 62423, annex C of IEC 60364-6, the field numbers of the SRT annex
other than 26, 27, 28, 30 and 32, the interval in AEA 90364-6 Ed. 2025 and the thermography ΔT table.

## What this guide does not replace
- The design, site supervision, signing of the protocol and the DCI or certificate are done by a qualified professional or installer according to the jurisdiction and its professional council.
- The AEA and IRAM regulations are paid, copyrighted documents: this guide summarizes and cites clauses, it does not replace the current text. In case of a discrepancy, the current regulation prevails.
- The utility decides on the service connection, the meter and the connection conditions; the municipality, on permits and approvals; the SRT and the ART (workers' compensation insurer), on compliance in workplaces.
