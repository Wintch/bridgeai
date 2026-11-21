---
title: Electrical panels (main, sub-panels, common services and construction site)
scope: panels in houses, apartments, condominium buildings (*propiedad horizontal*) and construction sites in Argentina; location, enclosure, minimum contents, assembly, single-line diagram, typical single-phase layout, sub-main circuit in buildings, three-phase panel, replacing old panels, inspection and maintenance
when_to_use: choosing or locating a panel; assembling, reviewing or replacing one; drawing or reading a single-line diagram; deciding how many circuits go on each RCD; protecting the sub-main circuit that runs up to an apartment; an RCD (ID) trips and the assembly is suspected; installing the construction site panel; switching off and locking out a panel to work on it
related: [README.md, regulations-and-permits.md, grades-and-circuits.md, conductors-and-conduits.md, protection.md, earthing.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md]
as_of: 2026-11-15
sources: [AEA 90364-7-770 Ed. 2017 and Corrigendum 1 (2018) (the one that was read; Ed. 2026 digital on sale and print on pre-sale with delivery from 2026-11-16), AEA 90364-7-771 Ed. 2006, AEA 90364-7-772 Ed. 2019, AEA 90364-7-704 Ed. 2026, Decreto 911/96 arts. 85-87, Res. SIyC 236/2024 (Anexo II as per Res. SIyC 26/2025) + Disposición DNRT 2/2025 (materials), Res. SIyC 237/2024 + Providencia DNRT PV-2025-120654504 (QR marking), IEC 61439-1/-3, IEC 60670-24 (current edition), IEC 60364-5-53 (section 534), manufacturer data sheets (Schneider Acti9, ABB S200)]
---
# Electrical panels

Rules for locating, choosing, assembling and documenting panels (distribution boards, *tableros*) on the job. Each rule has a stable ID so the agent,
a review or a job report can cite it ("does not comply with ELEC-TAB-6"). If a rule here conflicts with what the
utility (distribution company, *distribuidora*) or the municipality requires, their requirement governs for their part (service connection, metering, approval); if it conflicts with the
current AEA Reglamentación, the AEA governs and this guide gets corrected.

**Which edition applies (as of 2026-11-15).** For dwellings up to 63 A and up to 10 kA prospective short-circuit current
(persons BA2, evacuation BD1) the **AEA 90364-7-770 Edición 2017** applies (with its Corrigendum 1 of 2018); most of
the clauses cited here (770.x) come from that text. AEA already sells the **Edición 2026** of the 770 in digital form (print on pre-sale, with delivery
announced from 2026-11-16) and has not published an effective date: review every rule that cites 770 and mark the differences. Above
63 A, more than 10 kA, offices and shops, the **771 Ed. 2006** still applies; common areas and common services of buildings,
the **772 Ed. 2019**; construction sites and site compounds, the **704 Ed. 2026**. AEA standards are paid: here we summarize and cite the
clause, we don't copy.

**Safety first.** There are two kinds of tasks and they don't mix:
- **Dead** (assembling, wiring, tightening terminals, measuring continuity and insulation): with the supply cut, **locked with
  padlock and tag** and absence of voltage verified with a tester checked before and after (the five golden
  rules, ELEC-TAB-28 and [site-safety.md](site-safety.md), ELEC-SEG-3 and ELEC-SEG-4). Watch out: opening the main
  switch of a panel does **not** de-energize its incoming terminals or the line that feeds it. At the main
  panel, that can only be cut upstream, and upstream is the utility: you **request** the cut from them; their fuses,
  seals, meter and box are not touched (ELEC-NOR-15, ELEC-PRO-20).
- **Energized** (testing RCDs (*disyuntor* / *diferencial*) with an instrument, identifying what each lever cuts, measuring leakage with a
  clamp meter, thermography): done **only by trained personnel**, with a CAT III 600 V or CAT IV 300 V instrument as a minimum (ELEC-SEG-13)
  (ELEC-SEG-13), insulating gloves and face protection, **with the inner cover (dead front, *contratapa*) in place** whenever possible, measuring
  from a socket outlet or from accessible outputs. These checks are marked "(live)" in each rule.

Live work proper requires a specific authorization (Res. SRT 3068/2014) and **this guide does not
cover it**.

## Quick reference
| Situation | Rules |
|---|---|
| Which panel is it and which AEA section applies? | ELEC-TAB-1 |
| Where the main panel goes | ELEC-TAB-2, ELEC-TAB-3 |
| Where a sub-panel goes / mounting height / bathroom | ELEC-TAB-3 |
| Buying the enclosure (material, standard, certification) | ELEC-TAB-4, ELEC-TAB-5 |
| Inner cover, live parts, IP | ELEC-TAB-6 |
| Free space, spare capacity, heating | ELEC-TAB-7 |
| Signs, labels, single-line diagram | ELEC-TAB-8, ELEC-TAB-18 |
| What it must have inside, no exceptions | ELEC-TAB-9, ELEC-TAB-10, ELEC-TAB-11 |
| DIN rail mounting, supply terminals | ELEC-TAB-12 |
| Busbar comb (*peine*) or cable jumpers; comb with several RCDs (ID) | ELEC-TAB-13 |
| Two cables in one terminal, ferrules, torque | ELEC-TAB-14 |
| Neutral and earth terminal blocks | ELEC-TAB-15 |
| The RCD trips "by itself" or with loads from another circuit | ELEC-TAB-16 |
| Cable colors and dressing | ELEC-TAB-17 |
| Reading or drawing a single-line diagram (example of the 4-floor building) | ELEC-TAB-18 |
| How many circuits per RCD, RCD type | ELEC-TAB-19 |
| Condominium building (PH): meters, TP per unit, common services | ELEC-TAB-20, ELEC-TAB-23, ELEC-TAB-24 |
| Construction site panel | ELEC-TAB-21 |
| Final check before energizing | ELEC-TAB-22 |
| Sub-main circuit running up to an apartment (*depto*): RCD, Class II, conduit, voltage drop | ELEC-TAB-23 |
| Three-phase panel, pumps, gate, elevator | ELEC-TAB-24 |
| Voltage protector, generator set, inverter or UPS in the panel | ELEC-TAB-25 |
| Replacing an old panel (fuses, wood, no RCD, no earth) or the one in the photo | ELEC-TAB-26 |
| Mandatory inspections and maintenance | ELEC-TAB-27 |
| Switching off and locking out to work (the cut is on another floor) | ELEC-TAB-28 |

## Reference values
| Item | Value | Source |
|---|---|---|
| Max. distance meter (or collective cabinet) → main panel | 2 m, inside the property | AEA 90364-7-770:2017, 770.16.3.1 |
| Main panel enclosure | Class II insulation (double insulation), standardized and certified | 770.16.3.1 |
| Minimum IP of the main panel outdoors | IP54 | 770.16.3.1 |
| Minimum IP of any panel (770) | IP41 or IP31D | 770.16.4 |
| Accessible surfaces (barriers, inner cover) | IP3XD minimum | 770.16.4.1.1 b1) |
| Height of operating levers above the floor | between 0.40 m and 2 m | 770.16.4 |
| Free space in front of the panel | ≥ 0.9 m | 770.16.2.2 |
| Lighting in the panel area | ≥ 200 lx, measured 1 m above the floor at the front | 770.16.2.3 |
| Separation from gas outlets/valves | ≥ 50 cm | 770.17 |
| Free spare space | ≥ 20 % of capacity, in 18 mm modules | 770.16.4 |
| Interconnection with cables (no comb/busbar) | only in panels with up to 3 outgoing circuits | 770.16.4 |
| Electrical hazard symbol | IRAM 10005-1, height ≥ 40 mm | 770.16.2.1 |
| Legends | in Spanish, legible at 1 m from the front | 770.16.4 |
| TP incoming switch (770 scope) | circuit breaker, two-pole with both poles protected (single-phase) or four-pole (three-phase), ≤ 63 A | 770.16.5.3 |
| RCD for final circuits | IΔn ≤ 30 mA, not time-delayed | 770.14.2.3 |
| RCD between panels (indirect contact of the sub-main circuit) | IΔn ≤ 300 mA, selective ("S") recommended, with Ra ≤ 40 Ω | 770.14.3.2 b) |
| Protective earthing resistance (with RCD ≤ 30 mA or ≤ 300 mA) | Ra ≤ 40 Ω (permanent maximum value) | 770.14.3.2 a) and b) |
| Minimum cross-section of the protective conductor (PE) | 2.5 mm²; PE = S up to 16 mm² phase, 16 mm² between 16 and 35 mm², S/2 above | 770.14.4.5 and table 770.14.I |
| Conduit TP → first sub-panel and risers | minimum diameter R19/R20 (3/4"); recommended R25 (1") | 770.7.1 p) |
| Voltage drop from the TP | ≤ 3 % lighting and socket outlets; ≤ 5 % motors (15 % at starting); ≤ 1 % in the sub-main: recommended in the 770, mandatory in the 771 (which governs the apartment in a building) | 770.15.6 and note; 771.13 b) and note (ELEC-CON-9) |
| Current-carrying capacity, IRAM NM 247-3 cable in conduit, 2 loaded conductors, 40 °C | 1.5 mm²: 15 A; 2.5 mm²: 21 A; 4 mm²: 28 A; 6 mm²: 36 A; 10 mm²: 50 A | table 770.12.I |
| Grouping factor in the same wiring system | 2 single-phase circuits: 0.80; 3: 0.70 | table 770.12.II |
| Phase imbalance in three-phase sub-panels | ≤ 30 % recommended | 770.16.5.4 |
| Standard breaking capacity of a PIA | 3 kA, 4.5 kA, 6 kA, 10 kA; always ≥ prospective Icc at that point | IEC 60898-1; 770.15.2.2.2 (see ELEC-PRO-3) |
| Advised standing leakage downstream of an RCD | ≤ 30 % of IΔn (≈ 9 mA for 30 mA) | IEC 60364-5-53, 531.3.2 (via IET; see ELEC-TAB-19) |
| General RCD test (not "S") | does not trip at 0.5 IΔn; at IΔn ≤ 300 ms; at 5 IΔn ≤ 40 ms | IEC 61008-1 / 61009-1 (time table in protection.md; ELEC-MED-6) |
| Insulation resistance, circuits ≤ 500 V | ≥ 1 MΩ measured at 500 V DC | 770.19.5.2.1 and table 770.19.I as per Corrigendum 1 (2018); see ELEC-MED-4 |
| Total connection length of the SPD (line + SPD + earth) | ≤ 0.5 m | IEC 60364-5-53, section 534 (see ELEC-PRO-18) |
| Inspection of the works | 2 moments: before covering and before putting into service | 770.2.2 |
| Periodic inspection | every 5 years at most | 770.19.4.3 |
| Typical PIA terminal torque | 2 N·m (Acti9 iC60 ≤ 25 A); 3.5 N·m (iC60 32-63 A); 2.8 N·m (ABB S200) | manufacturer data sheets; always use the one for the model |

## Panel types

### ELEC-TAB-1: Name each panel (*tablero*) correctly and apply the AEA section that corresponds to it
- **Rule:** before designing or reviewing, identify the panel type and the applicable AEA section:
  - **Meter box/cabinet:** the utility's line arrives; it contains the meter; the main line leaves from there. The model is set by the utility; the meter pillar (*pilar*), niche or cabinet is built or installed by the user (with their installer) according to that specification. The **meter, the service connection (*acometida*) and the seals belong to the utility** and only the utility handles them.
  - **Main panel (TP):** receives the main line; has the main switch; sub-main or final circuits leave from it.
  - **Collective meter cabinet:** in buildings, it houses the meters of each unit (and the common services one); the compartments with the main switches of each unit **work as main panels**.
  - **General sub-panel (TSG):** fed from the TP by a single sub-main circuit; distributes to other sub-panels or final circuits (typical: the panel inside the apartment).
  - **Sub-panel (TS, *tablero seccional*):** any other panel fed by a sub-main circuit.
  - **Common services panel:** landing (*palier*), staircase, pumps, elevator, door entry system; section 772 (and 791 for elevators).
  - **Construction site panel:** temporary construction panel; section 704 and Decreto 911/96.
- **Why:** each type has different requirements (the TP requires Class II and distance to the meter; the sub-panel requires an incoming device suitable for isolation; the site panel, socket outlets protected by RCD ≤ 30 mA, ELEC-TAB-21). Confusing them leads to requesting or accepting what doesn't apply, or to expecting the utility to install a box that should have been built.
- **How:** with the incoming current, the prospective Icc (the utility provides it) and the use, choose 770 (dwelling ≤ 63 A and ≤ 10 kA), 771 (other dwellings, offices, shops), 772 (common areas), 704 (construction site). In the single-line diagram use the acronyms TP, TSG, TS, CS, CT. Ask the utility for its specification of pillar/niche and meter box before building.
- **Verify:** that the design states which AEA section applies and that the incoming switch current and the Icc are written on the single-line diagram (770-A.1.1 and 770-A.1.2).
- **Don't:** apply the 770 to a commercial shop or to an entire building; call the apartment panel the "main panel" when the real TP is on the ground floor next to the meter.
- **Source:** AEA 90364-7-770:2017, 770.1 (scope), 770.6 (lines), 770.16.1 a) to e) (panel types), table 770.15.I (metering box: design/choice by the utility; installation and responsibility "según lo exigido por la Autoridad de Aplicación" (as required by the enforcement authority)); Reglamento de Suministro ENRE (ENRE supply regulations), user obligations (see ELEC-NOR-15); preface of the 770 (what stays in the 771); AEA catalog (editions 771:2006, 772:2019, 704:2026, consulted 2026-11-15).

## Location

### ELEC-TAB-2: The main panel goes inside the property, no more than 2 m from the meter, and in a Class II enclosure
- **Rule:** the TP is installed inside the property at **≤ 2 m** from the meter box or the collective cabinet. Its enclosure has **Class II insulation**, standardized and certified, and is assembled respecting the double insulation; the main line and its conduit must also be Class II or have reinforced insulation. Outdoors, **IP54** as a minimum.
- **Why:** the main line (meter → TP) has no protection of the user's own; the shorter and better insulated it is, the lower the risk of an unprotected fault. Class II prevents a fault in that section from energizing the enclosure.
- **How:** place the TP next to the meter pillar or the meter niche; use double-insulated cable or single-core cable in insulating conduit (see [conductors-and-conduits.md](conductors-and-conduits.md)); a plastic enclosure with the double square symbol (IEC 60417-5172).
- **Verify:** measure the real meter → TP distance; look for the Class II symbol on the enclosure; check that no screw or metal part passes through it from side to side.
- **Don't:** put the TP at the back of the house with 15 m of main line; use a metal enclosure for the TP within the 770 scope. If the 2 m cannot be met, the location is agreed between designer, owner and utility/authority (note to 770.16.3.1), not decided by the installer alone.
- **Source:** AEA 90364-7-770:2017, 770.16.3.1. Some utilities and cooperatives set their own distances: **Not verified in a primary source:** one utility document found requires 1 m; check your utility's supply regulations.

### ELEC-TAB-3: Dry, accessible, lit location, away from gas and never in the bathroom
- **Rule:** all panels go in a dry location, normal environment, easy to access, away from water, gas and sewers. They are **not** allowed in bathrooms, inside furniture (cupboards, closets), under countertops, in cavities of the building or in hard-to-reach places. Leave **≥ 0.9 m** free in front, **≥ 200 lx** in the area and the operating levers between **0.40 m and 2 m** from the floor. Panels and outlet points (*bocas*) at **≥ 50 cm** from gas outlets or valves. In houses with more than one floor, one sub-panel per inhabited floor is suggested.
- **Why:** the panel is safety equipment: it must be possible to find and operate it quickly, in the dark if necessary, without climbing or emptying a closet. Moisture and gas near a device that sparks when switched is a dangerous combination.
- **How:** mark the location on the drawing before raising walls; near the entrance or the main circulation; with the highest row of devices below 2 m and the lowest above 0.40 m; an autonomous emergency light nearby is also recommended.
- **Verify:** tape measure: height of the highest and lowest lever, free space in front, distance to the gas valve; lux meter (or a cell phone reading as a rough guide) at 1 m from the floor.
- **Don't:** hide the panel behind a furniture door "because it's ugly"; put it above the kitchen countertop or over the water heater; block the front with a refrigerator.
- **Source:** AEA 90364-7-770:2017, 770.16.2.1 (location, bathrooms, furniture), 770.16.2.2 (0.9 m), 770.16.2.3 (200 lx), 770.16.4 (0.40-2 m), 770.17 (50 cm from gas). For the 771:2006 (clause 771.20) it is **not verified in a primary source** whether the heights match: consult it if the case falls under 771.
## Enclosure and construction requirements

### ELEC-TAB-4: Standardized, certified enclosure, sized for the assembly
- **Rule:** use a panel (distribution board, *tablero*) assembled according to IEC 61439-1 and IEC 61439-3, or an empty enclosure conforming to **IEC 60670-24** or **IEC 62208** assembled in compliance with IEC 61439-1/-3. The material may be metal or insulating, mechanically rigid, non-flammable, non-hygroscopic and with suitable dielectric properties. The devices (PIA, ID, switches, SPD (*DPS*)) must have the certification and conformity marking required by the current technical regulation.
- **Why:** the enclosure defines the protection against direct contact, the heat it can dissipate and its behavior in a fire. An enclosure without a standard has no declared dissipable power, and without that figure the temperature rise cannot be verified (ELEC-TAB-7).
- **How:** ask for the data sheet with: standard (IEC 60670-24 / IRAM 62670 or IEC 62208), number of 18 mm modules, IP, IK, Class II or not, maximum dissipable power (W). For the devices, the current regime is summarized in [regulations-and-permits.md](regulations-and-permits.md), ELEC-NOR-14: certified under the schemes set by Disposición DNRT 2/2025 and **conformity marking with seal and QR code** linking to the sworn declaration and the certificate (Res. SIyC 237/2024); scan the QR and confirm it matches the model.
- **Verify:** marking of the enclosure and of each device (standard, conformity marking, legible QR); that the declared dissipable power exists.
- **Don't:** use junction boxes, light boxes or "generic" enclosures without data; mount devices without conformity marking.
- **Source:** AEA 90364-7-770:2017, 770.16 (standards IEC 61439-0/-1/-3, IEC 60670-24, IEC 62208), 770.16.4 (materials) and 770.19.3.1 a) (materials with certification and mark when official resolutions require it); Res. SIyC 236/2024 with the Anexo II set by Res. SIyC 26/2025 (IF-2025-17295098-APN-DNRT#MEC: 4.2.11 enclosures IEC 60670-24, 4.2.12 enclosures IRAM 62670, 4.2.13 empty enclosures IEC 62208; 4.5.2 to 4.5.4 MCBs and RCDs; see [iram-standards.md](iram-standards.md) ELEC-IRA-2 and ELEC-IRA-12) and Disposición DNRT 2/2025 (BO 2025-04-15) with its annex IF-2025-38164600-APN-DNRT#MEC; Providencia DNRT PV-2025-120654504 (2025-10-30), "Marcado de conformidad - Res. SIyC 237/24" (conformity marking; conformity seal + QR code, items 3.1 and 3.2.2 of the annex to Res. 237/24). AEA cites IEC 60670-24 without a date, so the current edition applies; **Not verified in a primary source:** whether there is an Ed. 3.0 of 2024 that replaced Ed. 2.0 of 2011, and the exact correspondence between IRAM 62670 and IEC 60670-24 (Argentine manufacturers certify their enclosures "según IRAM 62670" (according to IRAM 62670)). Empty enclosures are in the current Anexo II (IEC 62208, 4.2.13), according to iram-standards.md.

### ELEC-TAB-5: Double insulation or metal with earth: choose one and stick to it to the end
- **Rule:** a **Class II** (insulating) panel is not earthed through its internal parts and must not be pierced by conductive parts; a **metal** panel has **all** its exposed conductive parts (body, door, inner cover (dead front, *contratapa*), mounting plate) bonded to the protective conductor.
- **Why:** Class II protects because nothing conductive and accessible can become live; a through screw or a metal rail that comes out to the outside breaks that protection. In the metal panel, the protection is automatic disconnection by RCD (*disyuntor* / *diferencial*), which only works if the exposed conductive part is earthed.
- **How:**
  - Class II: enclosure with the IEC 60417-5172 symbol visible; no metal screw from side to side; insulating cable glands and connectors; internal metal parts are **not** connected to the PE (there is no need to earth the rail, the lock or the metal hinges). The PE of the circuits still passes through the panel's earth terminal block.
  - Metal: door bonded to the body with a braid or green-yellow conductor, inner cover and mounting plate bonded to the earth terminal block (each with its own branch, not daisy-chained); continuity guaranteed between all exposed conductive parts.
- **Verify:** dead, continuity between door, body and PE terminal block in the metal panel (see [testing-and-commissioning.md](testing-and-commissioning.md)); in the Class II one, absence of conductive parts passing through the enclosure.
- **Don't:** fix a Class II enclosure with screws that stick out inside touching terminals; leave the door of a metal enclosure without its earth jumper "because the hinge makes contact".
- **Source:** AEA 90364-7-770:2017, 770.16.4 (double-insulated panel and rail/lock/hinges), 770.16.4.1.2 a) and b) I-V, 770.14.4.5 note (green-yellow branches, series connection of exposed conductive parts prohibited).

### ELEC-TAB-6: With the door open, nothing live can be touched
- **Rule:** panel degree of protection **IP41 or IP31D** as a minimum; **no live part accessible from outside, not even with the door open**; accessible surfaces (inner cover, barriers) **IP3XD** minimum; every live terminal covered by a barrier; covers and inner covers can only be removed **with a tool or key**.
- **Why:** the person who opens the door to reset an MCB (*térmica*) can be anyone, including children. In IP3XD, the digit 3 means that objects of 2.5 mm or more cannot enter, and the letter D, that a 1 mm diameter wire pushed through a slot **does not reach** any live part. In practice: neither a finger nor a thin screwdriver reaches a terminal. (Not letting even a 1 mm wire in corresponds to IP4X.)
- **How:** inner cover cut out to fit the devices (the cutout lets only the levers through); **blanking plates** on every empty module; incoming terminals and busbar combs (*peines*) with covers; no stripped cable outside the terminal.
- **Verify:** with the door open, go over the whole front: no copper or terminal should be visible; check that the inner cover doesn't come off by hand.
- **Don't:** use the panel without its inner cover "until the job is finished" with the installation energized; leave free modules uncovered; enlarge the cutout with a utility knife.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (IP41/IP31D, open door, tool, barriers) and 770.16.4.1.1 b1)-b3) (IP3XD). Meaning of digits and additional letter according to IRAM 2444 / IEC 60529 (770.6.6, note 3). For the enclosure IK the 770 sets no value in 770.16: choose it according to the risk of impacts (IEC 62262).

### ELEC-TAB-7: 20 % spare capacity and temperature-rise check
- **Rule:** leave **≥ 20 %** of the panel's capacity free, counted in 18 mm modules. Provide ample interior space for routing and bending the cables. Verify that the power dissipated by the devices does not exceed what the enclosure can dissipate.
- **Why:** without spare space, the next extension ends up as a panel hung next to it or two cables per terminal. A small, full enclosure heats up, the devices trip unnecessarily and the terminals age.
- **How:** calculation from the 770, annex 770-B.3:
  - P_tot = P_dp + 0.2 × P_dp + P_au, and **P_tot ≤ P_de** is required (declared and certified dissipable power of the enclosure).
  - **P_dp:** losses of the PIAs (manufacturer's data or, if none, the per-pole maximums of IEC 60898-1 reproduced in table 770-B.XI; see the table), multiplied by the utilization factor Ke (by convention 0.85) and the diversity (simultaneity) factor K (table 770-B.XII, according to the number of circuits). If the incoming device is an **RCD or a switch-disconnector**, the panel current is taken as equal to the sum of the outputs; the annex examples adopt **K = 1** (conservative).
  - **0.2 × P_dp:** connections, socket outlets, relays, RCDs and switch-disconnectors.
  - **P_au:** other devices not included above: bullseye pilot lights, bell transformers, etc.
  - Worked example with the TSG of the apartment from ELEC-TAB-18 (incoming switch-disconnector, K = 1; PIAs 2×10, 2×10, 2×16, 2×16 and 2×20 A; losses per pole 3 W up to 10 A, 3.5 W up to 16 A, 4.5 W from 16 to 25 A): P_dp = 2×(3 + 3 + 3.5 + 3.5 + 4.5) = 2 × 17.5 = **35 W**; P_tot = 35 + 0.2×35 + 0 = 35 + 7 = **42 W**. Choose an enclosure with **P_de ≥ 42 W**.
  - Spare space in the same panel: two-pole Q1 (2 modules) + ID1, ID2 and ID3 (2 + 2 + 2) + 5 two-pole PIAs (10) = **18 modules occupied**. With 20 % spare on the total capacity C: 18 ≤ 0.8 × C → C ≥ 22.5 → **24 modules minimum**. If there are SPDs with their backup protection or a voltage protector (ELEC-TAB-11, ELEC-TAB-25), add their modules according to the data sheet: for example, 4 more modules → 22 occupied → C ≥ 27.5 → the next commercial size (for example **36 modules**). Buy the commercial size that complies.
- **Verify:** total vs. occupied modules on the data sheet and on site; P_de on the enclosure data sheet.
- **Don't:** buy the enclosure "just right"; count the spare space on the rail and then fill that space with terminal blocks.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (20 %, 18 mm modules, interior space, thermal verification according to AEA IT 90890 / IEC 61439 / IEC 60670-24 / IEC 62208) and annex 770-B.3 (formula, Ke, table 770-B.XI, table 770-B.XII and examples with K = 1). The agent uses the `gateway electricidad` calculator so as not to do these calculations from memory.

### ELEC-TAB-8: Signposted, labeled and with the assembler's data
- **Rule:** on the front (frame, door or barrier) the IRAM 10005-1 **electrical hazard** symbol of **≥ 40 mm**, durable and always visible, and below it the function of the panel ("TABLERO PRINCIPAL" (main panel), "TS PLANTA ALTA" (upper floor sub-panel)). Each output identified. The panel carries indelible marking with: **manufacturer or responsible assembler**, **voltage** (single-phase/three-phase) and **maximum design Icc**. Everything in Spanish, legible at 1 m.
- **Why:** in an emergency someone who doesn't know the house has to know what that box is and what each lever cuts. The maximum Icc indicates whether devices added later have sufficient breaking capacity.
- **How:** printed or engraved labels (not ballpoint pen on paper tape); circuit name the same as on the drawing ("IUG1 dormitorios" (bedrooms), "TUG2 cocina" (kitchen)); a laminated single-line diagram inside the door is recommended (ELEC-TAB-18). An enclosure color that contrasts with the yellow and black symbol is recommended.
- **Verify:** that each lever has a label and that it matches what it really cuts. (Live, trained personnel:) when putting into service, open one PIA at a time and check with a tester or probe at the outlet points (*bocas*) that it cut what the label says.
- **Don't:** cover the symbol or the marking when flush-mounting or painting; label "varios" (miscellaneous).
- **Source:** AEA 90364-7-770:2017, 770.16.2.1 (symbol, durability, visibility) and 770.16.4 (manufacturer or assembler marking, Spanish, 1 m); Farina, "Ubicación de los tableros eléctricos" (location of electrical panels), Ingeniería Eléctrica, Feb 2022 (function legend under the symbol).

## Minimum contents

### ELEC-TAB-9: Main panel: a two-pole incoming circuit breaker and nothing single-pole
- **Rule:** the TP has at its head a **circuit breaker** that switches and protects (it may have an associated RCD), **≤ 63 A** within the 770 scope, **two-pole with protection on both poles** in single-phase (four-pole with all poles protected in three-phase). All incoming switches **isolate the neutral**. The PIAs are IEC 60898-1, two-pole, with simultaneous opening of the poles and **lockable in the open position** (seal or padlock). **Prohibited** in single-phase: single-pole PIAs, "1P+N", "neutro pasante" (through neutral) or "neutro no protegido" (unprotected neutral), and combined MCB-RCD devices with protection on only one pole.
- **Why:** in distribution networks the neutral can be live with respect to earth (or phase and neutral can come reversed from the network); if you cut only one pole, the "switched off" circuit can remain live. Locking in the open position is what allows you to put the padlock on and work without anyone resetting it (ELEC-TAB-28).
- **How:** if a single sub-main circuit leaves the TP, the incoming device is sized to protect it (overload and short circuit; indirect contact of the sub-main is solved separately, ELEC-TAB-23); if more than one circuit leaves, the incoming device protects the panel against overload and short circuit, and each output has its own PIA. Breaking capacity ≥ prospective Icc at the TP (with no data from the utility (distribution company, *distribuidora*), in a building meter cabinet don't go below 6 kA; ELEC-PRO-3). Sizing in [protection.md](protection.md).
- **Verify:** read the front of each device: two protected poles (markings on both poles), standard IEC 60898-1, In ≤ 63 A at the incoming device, breaking capacity, hole or accessory for a padlock.
- **Don't:** use an RCD alone as the TP incoming device (the RCD doesn't protect against overloads or short circuits); install "termomagnéticas de un módulo con neutro" (one-module MCBs with neutral) in a single-phase installation.
- **Source:** AEA 90364-7-770:2017, 770.16.5.1 (isolated neutral, prohibition of single-pole and 1P+N), 770.16.5.2 (IEC 60898-1, locking, simultaneous opening), 770.16.5.3 (TP incoming device, ≤ 63 A; for more, 771), 770.15.2.2.2 (breaking capacity ≥ Icc). 6 kA criterion with no data: practice, see ELEC-PRO-3.

### ELEC-TAB-10: Sub-panels: an isolating incoming device, a PIA per circuit and every final circuit under a 30 mA RCD (*disyuntor*)
- **Rule:** each sub-panel has an incoming device with guaranteed **suitability for isolation** (two-pole switch-disconnector, two-pole PIA with both poles protected, or RCD IEC 61008/61009). Each branch circuit has its own two-pole **PIA**. **All final circuits** are protected by an RCD of **IΔn ≤ 30 mA, not time-delayed**. The rated current of each RCD must be **≥** that of the overcurrent device in series upstream, **or ≥ the sum** of the PIAs below it.
- **Why:** isolation allows the panel to be de-energized for work. The 30 mA RCD is the additional protection against direct contact. Against indirect contact, in a TT system (mandatory on the public LV network) there are two accepted measures: **automatic disconnection**, and for that the **only accepted device is the RCD** (PIAs are not valid as protection against indirect contact), or **Class II** (double insulation, 770.14.3.1). An RCD has no thermal protection of its own: if more load is hung on it than it can handle, it burns out without tripping.
- **How:** example of the sum criterion: RCD 2×40 A with PIAs of 10 A and 20 A below → 10 + 20 = 30 A ≤ 40 A, complies; with 16 + 20 + 10 = 46 A > 40 A it does not comply by sum, and only complies if the series device upstream is ≤ 40 A. The breaking capacity and RCD/PIA short-circuit coordination are requested from the RCD manufacturer (coordination table: "protegido por PIA C hasta X A, Inc = 6 kA" (protected by C PIA up to X A, Inc = 6 kA)). Between panels a selective ("S") RCD ≤ 300 mA may be used for the sub-main circuit (ELEC-TAB-23).
- **Verify:** test button of each RCD (mechanical test) and, live and by trained personnel, an instrument test connected at a socket outlet of the circuit (not inside the panel): at 0.5 IΔn it must **not** trip; at IΔn it must trip in **≤ 300 ms**; at 5 IΔn in **≤ 40 ms** (general RCD; an "S" has longer times, see the time table in [protection.md](protection.md) and ELEC-MED-6). Record the values. Sum of PIAs per RCD noted on the single-line diagram.
- **Don't:** leave a circuit "outside the RCD" (*afuera del disyuntor*) (refrigerator, pump, alarm) so it doesn't trip: if a trip is a nuisance, look for the leakage or fit a dedicated RCD; don't remove the protection.
- **Source:** AEA 90364-7-770:2017, 770.16.5.4 (sub-panel incoming device and note 1), 770.14.2.3 (30 mA not time-delayed), 770.14.3.1 (Class II as a measure against indirect contact), 770.14.3.2 (TT: by automatic disconnection, only RCDs; 300 mA selective recommended), 770.15.2.2.5 (rated current and short circuit of the RCD), 770.19.3.1 g) (test by passing IΔn). Disconnection times: IEC 61008-1 / IEC 61009-1 (time table in protection.md and ELEC-MED-6).
### ELEC-TAB-11: SPD (*DPS*) where the table requires it, and space provided for an AFDD
- **Rule:** install surge protective devices (SPD, *DPS*) when required by table 770.15.III: **always** if the building has a lightning rod; **mandatory** if the supply is overhead (fully or partly) and the keraunic level exceeds 25 thunderstorm days per year, unless a risk analysis according to AEA 92305-2 justifies otherwise; the overhead-network requirement **does not apply** if the overhead line is made of insulated conductors with an earthed metal screen **or includes an earthed conductor** (note 2 of the table). It is not mandatory with a fully underground network, although it may be advisable for critical equipment. The 770 also **recommends** arc fault detection devices (AFDD) in the TP and in the sub-panels.
- **Why:** overvoltages from lightning and switching destroy electronics (inverter, TV, router, gate) and neither the MCB (*térmica*) nor the RCD (*disyuntor* / *diferencial*) stops them.
- **How:** the keraunic level is taken from the AEA 92305-11 maps. Reserve modules for the SPD and its backup protection (according to the manufacturer). In TT, if the SPD goes **upstream of the RCD**, use the **CT2** configuration ("1+1" in single-phase, "3+1" in three-phase: varistors between phase and neutral and a gas discharge tube between neutral and PE), so a failure of the SPD does not remain as an earth leakage without RCD protection; if it goes downstream of an RCD, prefer that RCD to be "S". Total length of the connections (from the connection point to the line, through the SPD and its backup, to the earth terminal block) **≤ 0.5 m**. Details in [protection.md](protection.md), ELEC-PRO-16 to ELEC-PRO-18.
- **Verify:** that the design states whether an SPD is required and why (network type, keraunic level, lightning rod); with a tape, the length of the connections; SPD status indicator in green.
- **Don't:** install an SPD with long, looped cables to the earth; put an SPD in a panel (distribution board, *tablero*) without earthing; put ordinary phase-earth varistors before the RCD in TT.
- **Source:** AEA 90364-7-770:2017, 770.15.4 and table 770.15.III with notes (2) to (4), final note of 770.16.5.4 (AFDD); AEA 92305 (series); IEC 60364-5-53, section 534 (configurations CT1/CT2, connection length ≤ 0.5 m), according to ELEC-PRO-18. **Not verified in a primary source:** the equivalent subclause number in AEA 90364-5-534.

## Neat assembly

### ELEC-TAB-12: Devices on DIN rail, vertical and fed from the top
- **Rule:** components go on rails, profiles or supports, **never** screwed directly to the back or side face of the enclosure; on the front face only what is seen or operated from outside. Switching and protection devices are mounted **vertically** and fed **through the top terminals**; if they are fed from below, a sign "**Precaución – Alimentación por bornes inferiores**" (Caution - Supply through bottom terminals) is fitted.
- **Why:** whoever works on the panel assumes that, with the device open, the bottom terminals are dead. Feeding from below without warning is a trap.
- **How:** 35 mm DIN rail (the standard for modular devices) firmly fixed; devices in the order of the single-line diagram, from left to right: incoming device, SPD, RCDs with their PIAs grouped.
- **Verify:** dead (locked out and verified), follow by eye the path of each device: input at the top, output at the bottom on all of them.
- **Don't:** hang devices from their own cables; mix devices of different RCDs (ID) in the same rail group without labels.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (mounting on supports, vertical position, top terminals and sign). 35 mm rail: manufacturers' practice (IEC 60715); **not verified in a primary source** as an AEA requirement.

### ELEC-TAB-13: Busbar comb (*peine*) or distribution busbar from 4 outputs up; cable jumpers only in small panels
- **Rule:** in panels with **up to 3 outgoing circuits** cable interconnections are allowed; with more, use a **busbar comb (insulated distribution busbar) or busbars**, rated for the current and of the same system as the devices. With two or more RCDs, **the comb is cut per group**: one section for the PIAs of each RCD, fed from the output of **that** RCD.
- **Why:** cable jumpers between many devices lead to two cables per terminal, uneven tightening and hot spots; the comb distributes with uniform contact and comes insulated (IPXXB). A continuous two-pole comb that runs from one group to another joins the phase and neutral terminals of all the devices it touches: it bypasses the input and output of the RCDs (defeating them) or parallels the neutrals of different groups, which is the shared-neutral case of ELEC-TAB-16 (trips, or circuits without real RCD protection).
- **How:** two-pole comb (phase and neutral) with pitch and manufacturer compatible with the devices; comb current ≥ that of the device feeding it; cut the comb with the tool and fit the end caps; free positions covered. The supply to the RCDs from the incoming device goes with its own comb section (which touches only the **inputs** of the RCDs) or with cable.
- **Verify:** that the rated current of the comb is shown on its packaging or data sheet and that it is ≥ the group's incoming device; that no teeth are left exposed; that no comb section touches at the same time the output of an RCD and devices of another group.
- **Don't:** "bypass" six MCBs with stripped 1.5 mm² cable daisy-chained; put a comb from one brand on devices from another that don't fit well; a comb running along the whole row with two RCDs in the middle.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (cable interconnections up to three outgoing circuits). Cutting the comb per RCD group: a consequence of the RCD principle (IEC 61008-1) and of ELEC-TAB-16; sizing the comb according to the manufacturer's data sheet: **not verified in a primary source** as AEA text.

### ELEC-TAB-14: One cable per terminal and factory torque (ferrules recommended on flexible cables)
- **Rule:** required: **only one conductor per terminal**, unless the terminal is designed for more (the data sheet says so). Recommended: terminate flexible conductors (class 5) with a **ferrule (tubular terminal)** crimped with pliers, and tighten each terminal to the **torque indicated by the manufacturer**, with a torque screwdriver.
- **Why:** two cables of different cross-section in a cage terminal end up one firm and the other loose; a flexible cable without a ferrule splays into strands and loses pressure over time. A loose terminal heats up, carbonizes and can start a fire; an over-torqued one breaks the cage or cuts strands.
- **How:** typical values published by manufacturers: Schneider Acti9 iC60, **2 N·m** up to 25 A and **3.5 N·m** from 32 to 63 A; ABB S200, **2.8 N·m**. These are examples: the value that counts is the one on the data sheet of the exact model. To join several cables, use a distribution terminal block or the comb, not the PIA terminal. Don't tin the ends of cables that go into screw terminals (recommendation of terminal manufacturers).
- **Verify:** dead, a firm tug on each cable after tightening; no loose strand outside the terminal; insulation reaching the terminal with no copper visible. To detect loose terminals in service: (live, trained personnel) thermography or an infrared thermometer with the panel under load and **the inner cover (dead front, *contratapa*) in place**, without touching anything; or re-check the torque with the supply cut upstream, locked out and absence of voltage verified (ELEC-TAB-28). **Never** "check by touch": the incoming terminals remain live even if the main switch is open.
- **Don't:** "fold into a U" a cable so it goes into the terminal doubled; tighten "all the way until it creaks"; reuse ferrules; touch terminals to see if they are warm.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (only one cable per terminal or clamp unless terminals are designed for it); torques: Schneider Electric Acti9 iC60 and ABB S200 technical data sheets (distributor copies consulted 2026-11; medium confidence). Ferrules, no tinning and torque screwdriver: **manufacturers' recommendation**, not verified AEA text.

### ELEC-TAB-15: Separate and identified neutral and earth terminal blocks
- **Rule:** the panel has an identified **earthing bar or terminal block** (earth symbol, letters PE or green-yellow), with one terminal for each incoming protective conductor, and the panel's earth leaves from there. The **neutral** has its own terminal blocks, separate from the earth one, and **one for each RCD group** (ELEC-TAB-16).
- **Why:** in a TT system neutral and earth are different conductors; if they are joined in the user's panel, part of the return current goes back through the PE and the RCD trips (or, worse, the exposed conductive parts become live).
- **How:** PE terminal block with enough terminals and with spare ones; the earthing conductor coming from the earth rod (*jabalina*) to that terminal block (see [earthing.md](earthing.md)); blue/light blue neutral terminal blocks, labeled "N – ID1", "N – ID2", with a cover (the neutral is a live conductor).
- **Verify:** dead, that there is no continuity between the neutral bar and the earth bar with the RCDs open and the installation disconnected from the network; that each circuit has its PE in the terminal block.
- **Don't:** jumper neutral and earth "so the three-pin socket outlet works"; use the neutral as earth; connect two PEs under the same screw if the terminal doesn't allow it.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (identified PE plate, bar or terminal block, with enough terminals), 770.14.4.6 (identification of earth terminals), 770.3 (TT system required) and 770.14.3.2 (TT). Neutral/earth separation in the user's panel is a consequence of TT; details in [earthing.md](earthing.md).

### ELEC-TAB-16: Each circuit with its own neutral, and never a neutral shared between RCDs
- **Rule:** each final circuit has **its own neutral**, which leaves from **its** two-pole PIA and from the **same** RCD as its phase. Neutrals are not shared between circuits, much less between circuits on different RCDs.
- **Why:** the RCD compares the current going out on the phase with the current coming back on the neutral **through the RCD itself**. If circuit A (under ID1) returns its current through the neutral of circuit B (under ID2), ID1 sees current that goes out and doesn't come back, and ID2 sees current that comes back without having gone out: both "read" a leakage.
  - Example (neutral of A connected to that of B): a 100 W load on A: I = P / U = 100 W / 220 V ≈ **0.45 A = 450 mA**, fifteen times the 30 mA of the RCD. It trips as soon as something is switched on. For a 30 mA RCD to possibly not trip, the imbalance would have to stay below IΔn/2 = 15 mA, that is a load of 220 V × 0.015 A ≈ **3.3 W** (a standby): a "small load" does not explain intermittent trips.
  - What is typical when it trips "sometimes" is that the neutrals of two circuits are **joined in a junction box** (in parallel): the return current splits between the two neutrals according to their resistance and each RCD sees only part of it. Example with a half-and-half split: a 10 W load (10 / 220 ≈ 45 mA) leaves ≈ 23 mA of imbalance, in the zone where a 30 mA RCD may or may not trip (between 15 and 30 mA); a 100 W load (≈ 455 mA) leaves ≈ 227 mA and always trips. That is why "it trips with the electric kettle but not with a lamp".
  - Also, with a shared neutral, when the PIA of circuit A is opened its neutral stays connected to circuit B, carrying current and live with respect to earth if B is in use: whoever works on A, thinking it is "cut", can get a shock.
- **How:** one neutral per circuit from the neutral terminal block of its RCD's group; in shared junction boxes, label the neutrals with the circuit number.
- **Verify:** dead (supply cut upstream, locked out and verified), open the two-pole PIAs of A and B, unplug the loads and measure continuity between the **bottom neutral terminals** of the two PIAs: there must be none. If there is, there is a jumper or a shared neutral downstream (see [troubleshooting-common-cases.md](troubleshooting-common-cases.md), ELEC-DIA-5).
- **Don't:** "save a cable" with a common neutral for two circuits in the same conduit; jumper neutrals of different RCDs in the terminal block.
- **Source:** operating principle of the residual current device and non-operating threshold 0.5 IΔn (IEC 61008-1); AEA 90364-7-770:2017, 770.16.5.1 (two-pole disconnection of each circuit) and 770.6.1 (circuits at least two-wire). **Not verified in a primary source:** an AEA clause that literally prohibits the shared neutral; the rule follows from the above.

### ELEC-TAB-17: Standard colors and dressed cables
- **Rule:** phase **brown** (L1; black L2, red L3), neutral **light blue/blue**, protective **green-yellow**. In single-phase the phase may be any of the phase colors; if it comes from a three-phase supply, the color of the source phase. Light blue/blue only for neutral and green-yellow only for PE. Cables are **dressed**: in neat bundles, parallel, with gentle bends, without crossing in front of the devices and without blocking ventilation.
- **Why:** a brown neutral or a light blue phase confuses the next person who works on it and causes accidents. A dressed panel can be reviewed in minutes and shows a burnt terminal.
- **How:** cable ties or internal slotted trunking; each cable with the right length and a small reserve; identification at both ends if another phase color had to be used out of necessity (never light blue, blue, green, yellow or green-yellow for another function).
- **Verify:** go over the panel: no light blue on a phase terminal and no green-yellow anywhere other than the PE terminal block.
- **Don't:** use green-yellow cable as a phase "because it was what there was"; leave loops of surplus cable inside the enclosure.
- **Source:** AEA 90364-7-770:2017, 770.10.3.8.5 and table 770.10.XIII (cable identification); 770.16.4 (space and bending radius).

## Single-line diagram

### ELEC-TAB-18: Each panel has its single-line diagram (*unifilar*), complete and matching what is installed
- **Rule:** the design includes the **single-line diagram of each panel** with: rated current, curve and breaking capacity of each device; IΔn (and type) of each RCD; cross-section of the main line, of each sub-main and final circuit and of the PEs; identification of each circuit; and design short-circuit current at each panel. Leaving a copy inside the panel is recommended.
- **Why:** it is the panel's "identity document": it allows replacing the correct device, extending without exceeding limits and verifying coordination. Without it, anyone puts a 32 A MCB on a 2.5 mm² cable.
- **How:** to read it, a single line is drawn per circuit even if it has 2 or 3 conductors (the small cross strokes indicate how many). It is read from top (supply) to bottom (loads). Next to each device: poles × current ("2×16 A"), curve ("C"), breaking capacity ("4,5 kA" / "4500"), IΔn and type ("30 mA, A"). Next to each line: cross-section and number of conductors ("2×2,5 mm² + PE 2,5 mm²") and destination. Symbols according to the enforcement authority; if it sets nothing, IRAM 4504.
- **Text example (the guide's case: building with ground floor (PB) + 4 floors with single-phase units, see [buildings.md](buildings.md); 2nd-floor apartment designed with the 771 (ELEC-EDI-26), **High** grade: 2 IUG + 2 TUG + 1 TUE for air conditioning. With a single IUG the sum (with the TUE) exceeds the Medium limit, the unit becomes High and High requires 2 IUG, 2 TUG and 1 TUE (table 771.8.II; ELEC-CIR-3, ELEC-CIR-4). DPMS ≈ 7 kVA: the calculator gives 6952 VA (31.6 A) with the outlet points of apartment 4A from [examples/README.md](examples/README.md); here it is rounded to 7000 / 220 ≈ 31.8 A; illustrative values to be verified with the calculator and with [grades-and-circuits.md](grades-and-circuits.md) and [conductors-and-conduits.md](conductors-and-conduits.md)):**
  ```text
  GRID 220 V ── METER (collective cabinet, ground floor; meter and seals: utility)
     └─ LP ≤ 2 m, Class II
        TP (the unit's compartment in the collective cabinet, ground floor, Class II)
          Q0   MCB 2×32 A curve C, Icn ≥ prospective Icc (no data: 6 kA)   [overload and short circuit of the CS]
          ID0  RCD 2×40 A, 300 mA, selective "S"                          [indirect contact on the CS; Ra ≤ 40 Ω]
          └─ CS: 2×10 mm² + PE 10 mm², single-core IRAM NM 247-3,
                 conduit ≥ R19/R20 (recomm. R25) up the riser, ≈ 12 m      [ΔU ≈ 0.67 %; ELEC-TAB-23]
             Apartment TSG (inside the unit, Class II, 24 modules or more; more if it has an SPD or a protector)
               Q1  Switch-disconnector 2×40 A (incoming, suitable for isolation)
               ├─ ID1 2×40 A, 30 mA, type A           Σ MCB = 10 + 16 = 26 A ≤ 40 A
               │    ├─ MCB 2×10 A C 4.5 kA → IUG1  living, balcony, bedroom lights   2×1.5 mm² + PE 2.5 mm²
               │    └─ MCB 2×16 A C 4.5 kA → TUG2  kitchen, laundry, bathroom sockets 2×2.5 mm² + PE 2.5 mm²
               ├─ ID2 2×40 A, 30 mA, type A           Σ MCB = 16 + 10 = 26 A ≤ 40 A
               │    ├─ MCB 2×16 A C 4.5 kA → TUG1  living and bedroom sockets        2×2.5 mm² + PE 2.5 mm²
               │    └─ MCB 2×10 A C 4.5 kA → IUG2  kitchen, laundry, bathroom, hall lights 2×1.5 mm² + PE 2.5 mm²
               ├─ ID3 2×25 A, 30 mA, type A           Σ MCB = 20 A ≤ 25 A
               │    └─ MCB 2×20 A C 4.5 kA → TUE1  inverter air conditioner         2×2.5 mm² + PE 2.5 mm², own conduit
               ├─ N terminal block for each ID; PE terminal block ← PE of the CS
               └─ spare ≥ 20 % (blanking covers)
  ```
  Notes on the example (worked calculations):
  - **Lights and socket outlets of the same area on different RCDs:** if a leakage in the kitchen socket outlets (TUG2) trips ID1, the kitchen lights (IUG2, on ID2) stay on, and the other way around in the living area. The inverter AC goes on its own ID3 (type A, or F if the manufacturer requires it; ELEC-TAB-19): its trips don't switch anything else off.
  - **Sum per RCD** (ELEC-TAB-10): 26 A, 26 A and 20 A, each one ≤ the In of its RCD (40, 40 and 25 A). Also Q0 (32 A) in series upstream is ≤ 40 A.
  - **TUE1 cable:** 20 A PIA on 2.5 mm² (Iz = 21 A in conduit, table 770.12.I): complies only in its own conduit. If it shares a conduit with another circuit: 21 A × 0.80 = 16.8 A < 20 A → does not comply; either its own conduit, or 4 mm² (28 A × 0.80 = 22.4 A ≥ 20 A). The 16 A TUGs with 2.5 mm² sharing conduit two by two: 16.8 A ≥ 16 A, complies (barely). 10 A IUG on 1.5 mm² grouped: 15 A × 0.80 = 12 A ≥ 10 A.
  - **PE:** never smaller than 2.5 mm² (that is why the IUG on 1.5 mm² has a 2.5 mm² PE); on the 10 mm² CS, PE = 10 mm² (table 770.14.I).
  - **Voltage drop on the CS:** ΔU = 2 · L · I · ρ · cos φ / S = 2 × 12 m × 31.8 A × 0.0214 Ω·mm²/m × 0.9 / 10 mm² ≈ 1.47 V → 1.47 / 220 ≈ **0.67 %** ≤ 1 % (required by the 771 on the sub-main; in the 770 it is a recommendation). With 6 mm² it would give 2.45 V ≈ 1.11 %: that is why 10 mm² was chosen. For the 4th floor (≈ 20 m), 10 mm² gives 1.11 % and does not comply; 16 mm² goes in (0.70 %) (ELEC-EDI-8). The calculator (`gateway electricidad drop --line submain`) gives slightly higher values because it uses class 5 cable at 70 °C.
  - **Icc at the TSG** (method of ELEC-PRO-3, with 6 kA at the ground floor): Zs = 220 V / 6000 A ≈ 0.0367 Ω; R of the CS = 2 × 0.0178 × 12 / 10 ≈ 0.0427 Ω; Icc ≈ 220 / (0.0367 + 0.0427) ≈ **2.8 kA** → 4.5 kA PIAs in the TSG with margin; at the TP, ≥ 6 kA.
  - **Heat and spare space of the TSG:** P_tot = 42 W (P_de ≥ 42 W) and 18 modules occupied → C ≥ 22.5 → 24-module enclosure (ELEC-TAB-7).
  - TUE ≤ 32 A, TUG ≤ 20 A, IUG ≤ 16 A are the maximums of table 770.6.I, not values to use without calculating; on the TUE, with 20 A socket outlets, the MCB doesn't go above 20 A ([current-ratings-and-devices.md](current-ratings-and-devices.md) ELEC-AMP-19).
  - The panel in the photo used as a case in this guide is a different one: three-phase, with a single RCD for about 27 circuits. How it is brought into line with these rules is in ELEC-TAB-26 and in the worked example in [reviewing-a-panel.md](reviewing-a-panel.md).
- **Verify:** that the single-line diagram matches what is installed (device by device) and that it has the design Icc; that the TP states "Montador responsable" (responsible assembler), voltage and Icc (ELEC-TAB-8).
- **Don't:** hand over the job without a single-line diagram or with a "typical" one that doesn't match the real panel.
- **Source:** AEA 90364-7-770:2017, annex 770-A.1.2 (contents of the single-line diagram; refers to IRAM 4504), table 770.6.I (maximum protection per circuit type), 770.7.4 and table 770.7.II (minimum circuits per grade; for the example apartment, AEA 90364-7-771:2006 table 771.8.II), table 770.11.I (minimum cross-sections), tables 770.12.I and 770.12.II (current-carrying capacity and grouping), 770.14.4.5 and table 770.14.I (PE), 770.15.6 (voltage drop). Keeping a copy inside the panel is a **recommendation of this guide**, not verified AEA text.
## Typical layout of a single-phase panel

### ELEC-TAB-19: Two-pole main switch → 2P 30 mA RCDs (*diferenciales*) → MCBs (PIA), with few circuits per RCD
- **Rule:** the typical order of a single-phase sub-panel (TS, *tablero seccional*) is: **two-pole incoming device** (switch-disconnector or PIA) → **SPD (*DPS*)** where applicable → **one or more two-pole 30 mA RCDs (ID, *diferencial*)** → **two-pole MCBs (PIA, *térmica*)**, one per circuit. The AEA allows one RCD per circuit or grouping several circuits under the same RCD; it sets no maximum number. This guide's criterion: **2 to 3 circuits per RCD**, and never more than the accumulated leakage allows.
- **Why:** any equipment with a filter or electronics (refrigerators, computers, power supplies, water heaters) lets a small permanent leakage current pass to earth. A 30 mA RCD can trip from half its IΔn (15 mA); that is why the accumulated leakage downstream should not exceed **30 % of IΔn ≈ 9 mA**. Many circuits on one RCD add up their leakage and cause trips "for no reason", and every trip leaves half the house without power.
- **How:**
  - Separate lighting from socket outlets on different RCDs (or spread the IUG circuits across RCDs); put equipment sensitive to outages (refrigerator) on an RCD with few loads; put outdoor, pool or damp circuits on their own RCD when possible. Each RCD with its own neutral terminal block (ELEC-TAB-15, ELEC-TAB-16) and a rated current that meets ELEC-TAB-10.
  - **RCD type:** **type A at minimum** where there are electronics (inverter AC or inverter refrigerator, washing machine, induction cooktop, chargers, LED); type F with single-phase variable speed drives; type B where smooth DC may occur (EV charger without DC detection). Type AC only for loads without power electronics. The "super-immunized" versions (Si/SI) reduce nuisance tripping. Details in [protection.md](protection.md), ELEC-PRO-9, and [special-installations.md](special-installations.md), ELEC-ESP-2.
  - **Selectivity (discrimination) between RCDs:** two 30 mA RCDs in series are not selective. If there is an RCD upstream (for example, the ID0 of the sub-main (feeder) circuit, ELEC-TAB-23), for only the downstream one to trip, that upstream RCD must be **selective type "S" and of higher IΔn** (≤ 300 mA): it is a technical condition for selectivity, and the AEA **recommends** it.
- **Verify:** dead, insulation resistance per circuit as an estimate of leakage (ELEC-MED-4). (Live, trained personnel, CAT III, gloves and face protection:) leakage current per group with a leakage clamp meter around L+N of an accessible outgoing line, without removing the inner cover (dead front, *contratapa*) if possible, with the usual loads connected (see [testing-and-commissioning.md](testing-and-commissioning.md)); if it approaches 9 mA, redistribute circuits.
- **Don't:** hang all 8 circuits of the house on a single 25 A RCD; put two 30 mA RCDs in series expecting "the downstream one to trip"; use type AC on the inverter AC circuit.
- **Source:** AEA 90364-7-770:2017, 770.16.5.4 a) and note 1 (RCD per circuit or grouped), 770.14.3.2 b) (≤ 300 mA, selective recommended). 30 % of IΔn limit: IEC 60364-5-53, 531.3.2, according to an IET commentary (Wiring Matters, 2021-2022); **not verified in the IEC text**. RCD types: IEC 61008-1 / IEC 62423 and AEA per ELEC-PRO-9. The figure of 2-3 circuits per RCD is **this guide's practical criterion**, not a normative requirement.

## Buildings and construction sites

### ELEC-TAB-20: Condominium building (*propiedad horizontal*): collective meter cabinet, TP per unit, TSG in each apartment (*depto*) and a separate common-services panel
- **Rule:** in a building (example: ground floor (PB) + 4 floors, single-phase supply per unit) the meters go in the **collective meter cabinet** (*gabinete colectivo*) defined by the utility; each unit's main switch, in its compartment at ≤ 2 m from the meter, acts as the **main panel (TP)** (ELEC-TAB-2, ELEC-TAB-9); from there a **sub-main circuit** (*circuito seccional*) rises to a **TSG (general sub-panel, *tablero seccional general*) inside each apartment** (ELEC-TAB-10, ELEC-TAB-19). That sub-main circuit is protected from the ground floor against overload and short circuit (incoming PIA) **and against indirect contact** (RCD ≤ 300 mA "S" in the compartment, or a Class II sub-main; ELEC-TAB-23). Common loads (landing and stair lights, pumps, door entry system, elevator) are fed from a **common-services panel** (*tablero de servicios generales*) supplied by its own meter, per AEA 90364-7-772 (and 791 for elevators), which is generally **three-phase** even if the units are single-phase (ELEC-TAB-24).
- **Why:** each unit must be able to be disconnected without affecting the others or the common services, and the longest and least supervised section of each unit's installation (the riser, *montante*) cannot be left without protection against indirect contact.
- **How:** risers and junction boxes per landing (*palier*) according to [buildings.md](buildings.md) (ELEC-EDI-7); in the collective cabinet, identify each switch with its unit ("2.º B") and the sub-main at both ends; the apartment's TSG near the unit's entrance (ELEC-TAB-3). Landing lights with a staircase timer (*automático de escalera*, *minutero*) or sensors, fed from the common-services panel (ELEC-EDI-15). Voltage protector (over/undervoltage relay) against broken (lost) neutral for each unit (ELEC-TAB-25, ELEC-EDI-11).
- **Verify:** (live, trained personnel) that each switch in the collective cabinet is labeled with the correct unit: open **one at a time** and check with a voltage tester, at that unit's TSG, for absence of voltage; record it. Dead: that the PE reaches each TSG (continuity to the main earthing bar).
- **Don't:** feed the landing lights from an apartment's panel; put the unit's TSG on the common landing; work in an apartment trusting only the label at the ground floor (ELEC-TAB-28).
- **Source:** AEA 90364-7-770:2017, 770.16.1 c) (collective cabinet; compartments as TP), 770.16.3.1 (2 m), 770.16.5.3 (each sub-main circuit protected against direct and indirect contact, short circuits and overloads); AEA catalog (772 Ed. 2019 "Instalaciones de espacios comunes y servicios generales" (installations in common areas and common services); 791-T1 Ed. 2018 elevators). **Not verified in a primary source:** the specific requirements of the 772 for the common-services panel (I could not read its text).

### ELEC-TAB-21: Construction-site panel (*tablero de obra*): earthed, socket outlets with RCD (*diferencial*), closed, fixed and inspected
- **Rule:** the construction-site panel is designed as a permanent installation per AEA; it has **earthing** of all its exposed conductive parts **and also** **automatic disconnection** (MCB and RCD): both, not one or the other. Socket outlets up to 32 A protected by an **RCD ≤ 30 mA**; enclosure suitable for outdoor use and impacts, with door and lock; socket outlets with earth; fixed to a structure at operating height, never resting on the ground; and inspected periodically. If a protective device operates for no known cause, **it is not reset** until the installation has been checked.
- **Why:** on a site there is water, mud, Class I hand tools, cables that get stepped on and people who are not electricians plugging things in. It is the panel that sees the most accidents.
- **How:**
  - The temporary construction supply is arranged with the utility (meter pillar (*pilar*) and site meter per its regulations).
  - Enclosure with an IP rating for outdoor use (as a reference, an outdoor TP requires IP54 in the 770), covers on the socket outlets, IEC 60309 industrial socket outlets with earth for tools.
  - Extension leads of double-insulated flexible cable for heavy duty (type H07RN-F outdoors), with an earthed plug and socket at the ends and **no taped splices** (ELEC-SEG-15).
  - Prefer Class II tools (double insulation); Class I tools always with PE (ELEC-SEG-16).
  - Own earth rod (*jabalina*) and measurement of earthing (PAT) and of continuity of exposed conductive parts with the protocol of Res. SRT 900/2015; panel supply cables overhead (≥ 2.40 m indoors per Dec. 911/96) or protected; electrical hazard signs; key held by the person in charge.
  - Before working on the line: de-energize, verify and treat it as if it were live. More in [site-safety.md](site-safety.md), ELEC-SEG-14 to ELEC-SEG-16.
- **Verify:** test button of each RCD at the start of each workday (recommended practice); condition of cables, plugs and extension leads; a current SRT 900/15 protocol for the site.
- **Don't:** "extension leads" made of two-wire cord without earth; plug in with bare wires stuck into the socket outlet; leave the panel open or on wet ground; bypass the RCD because it "trips with the concrete mixer".
- **Source:** Decreto 911/96, art. 86 (installation per AEA; "la totalidad de la instalación eléctrica deberá tener dispositivos de protección por puesta a tierra de sus masas activas. Además se deberán utilizar dispositivos de corte automático" (the entire electrical installation shall have protective devices by earthing of its exposed conductive parts; automatic disconnection devices shall also be used); de-energize and check before working; 2.40 m; equipment and tools with automatic disconnection switches and metal parts earthed) and art. 87 (maintenance; check before resetting a protection that operated for no known cause); Res. SRT 900/2015 (earthing protocol). Res. SRT 231/96 (condiciones básicas de higiene y seguridad en la construcción (basic health and safety conditions in construction), site safety file): **Not verified in a primary source:** that it contains specific requirements on construction-site panels. AEA 90364-7-704 Ed. 2026: **not verified in a primary source** (I could not read the text); the requirement of RCD ≤ 30 mA for socket outlets up to 32 A comes from IEC 60364-7-704:2017, which the AEA adapts, and the internationally standardized construction-site panels are the "ACS" of IEC 61439-4. Arranging the construction supply with the utility: common practice, not verified in a specific regulation.

### ELEC-TAB-22: Final check of the panel before energizing
- **Rule:** no panel is energized without a visual inspection and the initial tests done **dead**, and without the RCD tests once energized.
- **Why:** assembly errors (loose terminal, crossed neutral, PE not connected) are found in minutes with the panel open and dead; once the job is handed over they cost a fire or an electric shock.
- **How:** short checklist (the full procedure is in [reviewing-a-panel.md](reviewing-a-panel.md) and [testing-and-commissioning.md](testing-and-commissioning.md)):**
  1. Materials with a standard and conformity marking (ELEC-TAB-4); location, construction features and inscriptions of the TP and of each sub-panel (770.19.3.1 k).
  2. Torque of all terminals, one wire per terminal, ferrules (ELEC-TAB-14).
  3. Colors, neutrals per RCD group, busbar comb (*peine*) cut per group, separate terminal blocks (ELEC-TAB-13, ELEC-TAB-15 to 17).
  4. PE continuity from the terminal block to each circuit and, in metal panels, to the door and body (ELEC-TAB-5).
  5. Insulation resistance (ELEC-MED-4): with the supply disconnected and locked out, appliances unplugged, lamps, SPDs, voltage protectors and electronic equipment disconnected, and switches and PIAs **closed**; 500 V DC megohmmeter (megger); four measurements: between phases (in three-phase), phases joined together to neutral, phases joined together to PE, and neutral to PE. Minimum **1 MΩ** per circuit (table 770.19.I of Corrigendum 1; the original 2017 text said 0.5 MΩ). Don't touch conductors or probes during the test and **discharge** each circuit when finished. Earthing value according to [earthing.md](earthing.md) (Ra ≤ 40 Ω, ELEC-TAB-23).
  6. Inner cover fitted, blanking plates in place, no accessible live parts (ELEC-TAB-6).
  7. Labels, single-line diagram, hazard symbol, assembler's details (ELEC-TAB-8, ELEC-TAB-18).
  8. Energized (live, trained personnel): test button of each RCD and test with an instrument from a socket outlet: does not trip at 0.5 IΔn, trips at IΔn in ≤ 300 ms and at 5 IΔn in ≤ 40 ms (general RCD); check that each PIA disconnects what its label says (ELEC-TAB-8).
- **Verify:** that a written record of the measurements is kept (date, instrument, values) and that the inspection prior to commissioning has been requested (ELEC-TAB-27).
- **Don't:** "test by switching on to see if it trips"; run an insulation test (*megar*) with electronics connected.
- **Source:** AEA 90364-7-770:2017, 770.19.2 (preliminary inspections, includes panels in walls), 770.19.3.1 (initial inspection; k) panels; g) RCD test with IΔn), 770.19.5.2 (conditions and the four insulation measurements) and 770.19.5.2.1 with table 770.19.I per Corrigendum 1 (2018) (see ELEC-MED-4); AEA 90364-6 Ed. 2025 (verification of installations). RCD times: IEC 61008-1 / 61009-1.

### ELEC-TAB-23: The sub-main circuit rising to the apartment: protected against indirect contact, in conduit of sufficient diameter and with low voltage drop
- **Rule:** the sub-main circuit TP → TSG (in a building, the one that rises up the riser from the collective cabinet) must be protected against direct and indirect contact, short circuit and overload. The incoming PIA covers overload and short circuit, **but not indirect contact**. For that there are two ways:
  - (a) **RCD with IΔn ≤ 300 mA**, **selective "S"** recommended, in the TP compartment, upstream of the sub-main, with **Ra ≤ 40 Ω**; or
  - (b) sub-main in **Class II** along its entire route: cable with a 1 kV sheath (IRAM 2178-1 or IRAM 62266), or IRAM NM 247-3 single-core cables in **insulating** conduit and boxes (IRAM 62386 / IEC 61386), with no metal raceway in any section.
  The conduit TP → first sub-panel (including the riser conduit) is **R19/R20 (3/4") at minimum**, **R25 (1")** recommended. The voltage drop in the sub-main does not exceed **1 %** (mandatory in the 771, which is the one that governs an apartment in a building; recommended in the 770), within the 3 % total (ELEC-CON-9). The actual conduit diameter comes from the fill (table in [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-12; [buildings.md](buildings.md) ELEC-EDI-7): in medium-weight steel, 2 × 6 mm² + PE goes in RS 22, 2 × 10 mm² + PE in RS 25 and 2 × 16 mm² + PE in RS 32, so the 3/4" minimum is only enough for small cross-sections.
- **Why:** the sub-main runs through floors, junction boxes and common shafts, often in steel conduit; an insulation fault there energizes conduits and boxes, and in TT no PIA disconnects that leakage (the earth fault current is small compared to its magnetic trip). The "S" RCD disconnects without breaking selectivity with the apartment's 30 mA RCDs. A conduit bigger than the minimum lets you pull the cross-section the voltage drop calls for (10 mm² in RS 25, 16 mm² in RS 32) and expand later.
- **How:**
  - Example (ELEC-TAB-18): Q0 PIA 2×32 A + ID0 2×40 A 300 mA "S" (RCD In of 40 A ≥ the 32 A of the PIA in series, ELEC-TAB-10). Ra = 40 Ω maximum: with IΔn = 0.3 A, the touch voltage stays at 0.3 A × 40 Ω = **12 V**, below the 24 V limit.
  - If you choose Class II, write it on the single-line diagram ("CS Clase II, 770.14.3.1 b)", i.e. Class II sub-main circuit) and specify insulating conduit and boxes in the specifications (*pliego*); metal parts in contact with that raceway are not exposed conductive parts, but they are equipotentially bonded.
  - Voltage drop: ΔU = 2 · L · I · ρ · cos φ / S (worked example in ELEC-TAB-18 and ELEC-EDI-8). The agent uses `gateway electricidad drop` and `gateway electricidad size`.
- **Verify:** single-line diagram with the sub-main's RCD (IΔn, "S") or the Class II declaration; on site, that there are no metal conduit sections if Class II was declared; Ra measurement and ID0 test with an instrument (live, trained personnel); conduit diameter printed on it (R19/R20 or larger).
- **Don't:** consider the sub-main protected "because it has an MCB at the ground floor"; declare a steel-conduit riser as Class II; put the 10 mm² sub-main in 5/8" conduit.
- **Source:** AEA 90364-7-770:2017, 770.16.5.3 (each sub-main circuit protected against direct and indirect contact, short circuits and overloads), 770.14.3.1 a) and b) (installations considered Class II), 770.14.3.2 (TT: for automatic disconnection, RCDs only; b) ≤ 300 mA between panels, selective recommended, Ra ≤ 40 Ω, 24 V), 770.7.1 p) (R19/R20, R25 recommended, includes risers), 770.15.6 and note (3 % and 1 % recommended in sub-mains).
### ELEC-TAB-24: Three-phase panel (common services, pumps, gate, elevator, three-phase houses)
- **Rule:** a panel supplied in three-phase has a **four-pole** incoming device (in the main panel (TP), a circuit breaker with all poles protected; in sub-panels (TS, *tablero seccional*), a four-pole switch-disconnector, a four-pole circuit breaker or an RCD (ID, *diferencial*) to IEC 61008/61009), colors L1 brown, L2 black, L3 red, N light blue, PE green-yellow, and the 220 V circuits **spread across the three phases** with an imbalance that is recommended not to exceed **30 %**. If the neutral has a smaller cross-section than the phases, it needs its own protection. Each motor (pump, gate, ventilation) has a control device that disconnects all poles and **its own overload protection** (motor protection circuit breaker (*guardamotor*), or contactor with thermal overload relay).
- **Why:** with all the loads on one phase, that phase and the neutral are overloaded while the others run empty; in buildings that ends in hot neutrals and in the broken (lost) neutral that burns out appliances (ELEC-EDI-11). The circuit's MCB (PIA, *térmica*) does not protect the motor against running on two phases or a locked rotor: the motor protection circuit breaker does that.
- **How:**
  - Common services of the example building: three-phase TP with its meter; sub-panels per system (pumps, elevator, landings/emergency, door entry system/gate), according to ELEC-EDI-12. Pumps with motor protection circuit breaker, level control and dry-run protection (ELEC-EDI-14); elevator with a dedicated supply up to its panel (ELEC-EDI-13); gate with its own circuit, its own RCD and photocells (ELEC-EDI-17).
  - Spread the 220 V circuits per phase on the single-line diagram and write down the estimated current of each phase. Example: L1 = 30 A, L2 = 24 A, L3 = 21 A → imbalance = (30 − 21) / 30 = **30 %**, at the recommended limit; move a circuit from L1 to L3.
  - RCDs: one four-pole RCD per group, or two-pole RCDs per circuit taken from each phase with its neutral; type A or F/B depending on the variable speed drives (ELEC-PRO-9). With a three-phase busbar comb (*peine*), same criterion of cutting it per RCD group (ELEC-TAB-13).
- **Verify:** (live, trained personnel) current per phase with a clamp meter under normal load and calculation of the imbalance; phase sequence before starting pumps and elevator (ELEC-MED-7); setting of the motor protection circuit breaker to the motor's nameplate current.
- **Don't:** hang all the lights and socket outlets on a single phase "because the comb was handier that way"; protect a pump with only a PIA; install a thinner neutral without protection.
- **Source:** AEA 90364-7-770:2017, 770.16.5.3 (four-pole with all poles protected in three-phase), 770.16.5.4 (sub-panel incoming device, neutral protection, imbalance ≤ 30 % recommended), 770.7.1 n) (aim for a balanced system), table 770.10.XIII (colors); [buildings.md](buildings.md) ELEC-EDI-10 to ELEC-EDI-17 and [special-installations.md](special-installations.md) ELEC-ESP-14 (motors). **Not verified in a primary source:** the particular requirements of the 772 and the 791 for these panels.

### ELEC-TAB-25: Space in the panel for the voltage protector and for source changeover
- **Rule:** the 770 leaves protection against **permanent overvoltages** to the designer's judgment; in buildings and networks with a shared neutral, this guide recommends a **voltage protector** (over/undervoltage relay with its contactor or switch) in each unit's panel, after the incoming device. If there is a **generator set, hybrid inverter or UPS** supplying part of the installation, changeover is done with an **interlocked changeover switch** (manual or automatic) that prevents connecting the own source to the grid at any time, and the panel carries a "dos fuentes" (two sources) sign.
- **Why:** a broken neutral in the grid or in the riser (*montante*) puts 380 V on some apartments and burns out everything plugged in; the SPD (*DPS*) and the RCD do not prevent it. A generator connected without an interlock backfeeds the grid and can electrocute someone working on it "dead", besides burning out the generator when the grid comes back.
- **How:** reserve modules for the protector (per the data sheet) and add them to the spare-space calculation (ELEC-TAB-7). Set the maximum above the normal variations of the grid (not at 240 V or less) with a reconnection delay. For alternative sources: three-position changeover switch (grid-0-generator) or automatic one with mechanical and electrical interlock, disconnecting phase and neutral; details in [special-installations.md](special-installations.md), ELEC-ESP-23 to ELEC-ESP-27, and [protection.md](protection.md), ELEC-PRO-19.
- **Verify:** that the single-line diagram shows the protector and the changeover switch; that the changeover switch does not allow, in any position, joining the grid and the own source. **Before working on a panel with its own source, switch off and lock out all sources** (grid, generator, inverter, batteries, UPS) and verify absence of voltage on each one (ELEC-TAB-28, ELEC-SEG-6).
- **Don't:** connect the generator to a socket outlet with a "ficha macho-macho" (male-to-male plug); use two separate MCBs as a "changeover switch"; trust that there is no voltage with the main switch open if there is an inverter or UPS.
- **Source:** AEA 90364-7-770:2017, 770.15.5 (permanent overvoltages at the designer's judgment); voltage protector recommendation and changeover rules per ELEC-PRO-19, ELEC-EDI-11, ELEC-ESP-25 and ELEC-SEG-21 of this guide. The voltage protector in each unit is **this guide's criterion**, not a requirement of the 770.

### ELEC-TAB-26: Replacing or upgrading an old panel (and the one in the photo)
- **Rule:** a panel with plug fuses or porcelain **fuses** as circuit protection, a **wooden base** or unearthed sheet metal, **no RCD**, a single cable color, no inner cover (dead front, *contratapa*), or **a single RCD for the whole house** is replaced or rebuilt to meet the rules of this guide; you don't just "add an RCD (*disyuntor*)" on top and call it done. The immediate minimum: inner cover with no live parts, two-pole (or four-pole) incoming device, two-pole PIAs per circuit, 30 mA RCD on all final circuits, PE and earthing verified.
- **Why:** it is the most common case in renovations. Fuses get "reinforced" with wire and don't disconnect; wood chars; without earth the RCD protects only partly; with everything under one RCD, the trips lead people to bypass it.
- **How:**
  1. Survey before buying: number of actual circuits, cross-sections (if a circuit has 1.5 mm² with a 20 A PIA, lower the protection or rewire, ELEC-PRO-4), presence of PE in each circuit, condition of the earthing, whether it is single- or three-phase (ELEC-REV-4).
  2. Outage requested from the utility if the main line or the TP input has to be touched; if not, switch off the TP and lock it out (ELEC-TAB-28).
  3. New enclosure with the spare space and dissipable power of ELEC-TAB-7; neutrals identified per circuit before disconnecting anything (label each cable as you remove it).
  4. Insulation-test each old circuit before reconnecting it (ELEC-TAB-22): the ones that don't reach 1 MΩ are repaired before putting them under an RCD, or they will trip.
  5. NH fuses or plug fuses of the utility are not touched (ELEC-PRO-20).
  - **The panel in the photo** (worked example in [reviewing-a-panel.md](reviewing-a-panel.md)): three-phase, with an RCD 4P 63 A 30 mA, a 4P C40 main breaker and about 27 two-pole PIAs under that single RCD, cable jumpers in rows of 9 and 10 devices, no inner cover in the photo, solid-green conductors and free DIN rail. Brought into line with these rules: inner cover and blanking plates now (ELEC-TAB-6); split into groups of 2-3 circuits per RCD, lights and socket outlets on different RCDs, pool, gate and outdoor circuits on their own RCDs (ELEC-TAB-19); if the general 4P RCD is kept, it becomes 300 mA "S" (ELEC-TAB-19); busbar combs per group instead of jumpers (ELEC-TAB-13); one neutral terminal block per RCD (ELEC-TAB-15); measured phase distribution (ELEC-TAB-24); breaking capacity against the actual Icc (ELEC-TAB-9); recalculate spare space and heating: with more RCDs a larger enclosure or a second sub-panel will probably be needed (ELEC-TAB-7). For the single-phase apartment in the building, the equivalent is the TSG of ELEC-TAB-18.
- **Verify:** after the change, the full check of ELEC-TAB-22 and the record of measurements; if the rework changes the power or the TP incoming device, a new DCI (installation conformity declaration) may be required (ELEC-NOR-10).
- **Don't:** put an RCD in front of a panel with fuses reinforced with wire; reuse cables with cracked rubber insulation; reconnect without identifying the neutrals (the shared neutrals of ELEC-TAB-16 show up).
- **Source:** AEA 90364-7-770:2017, 770.16.5.1 to 770.16.5.4 (content of TP and sub-panels), 770.14.2.3 (30 mA), 770.16.4 (enclosure, spare space, inner cover); [troubleshooting-common-cases.md](troubleshooting-common-cases.md), ELEC-DIA-17 (old installations); worked example in [reviewing-a-panel.md](reviewing-a-panel.md). The order of priorities is **this guide's criterion**.

### ELEC-TAB-27: Inspection by the authority (*fiscalización*), periodic inspection and maintenance of the panel
- **Rule:** the site manager or the installer requests the **inspection** (*fiscalización*) from the enforcement authority at least at **two moments**: before covering conduits and embedded elements, and before commissioning. The initial inspection includes checking the **location, construction features and inscriptions** of the TP and the sub-panels. The installation is inspected periodically **every 5 years at most** (visual, test button of each RCD, PE continuity, insulation, earthing). The user presses the **test button of each RCD once a month**.
- **Why:** terminals loosen with thermal cycling, RCDs seize if they never operate, and "rushed" additions pile up. What is not checked, nobody finds out about until the fire.
- **How:** maintenance at every inspection: (dead, switched off and locked out) retightening of terminals to the data sheet torque and cleaning; (live, trained personnel, inner cover in place) thermography under load, RCD test with an instrument; record with date, values and who did it, kept with the single-line diagram. In buildings, the owners' association (*consorcio*) keeps the common-services record.
- **Verify:** the report or certificate of the two inspections; date of the last periodic inspection (≤ 5 years); that the user knows where the test button is and what to do if the RCD does not trip (call, don't keep using it).
- **Don't:** hand over without requesting the inspection before covering; "tighten the screws" of the panel while it is live.
- **Source:** AEA 90364-7-770:2017, 770.2.2 (inspection at two moments), 770.19.3.1 k) (visual inspection of panels), 770.19.4.1 to 770.19.4.3 (periodic inspection, maximum interval 5 years); Decreto 911/96 art. 87 (on sites, periodic checks); monthly test: manufacturer's legend on the RCD and ELEC-MED-15. The frequency of retightening and thermography is **this guide's criterion**.

### ELEC-TAB-28: To work on a panel: switch off, lock out, verify, even if the switch-off point is on another floor
- **Rule:** before opening or working on a panel or its circuits, apply the **five golden rules**: (1) **disconnect all sources** (including generator, inverter, UPS); (2) **lock** the open device with a padlock and a "Prohibido maniobrar" (do not operate) tag with the name of the person in charge; (3) **verify absence of voltage** with a tester proven on a known source before and after; (4) **earth and short-circuit** where applicable; (5) **signpost and cordon off**. Disconnection of the service drop, the meter or a sealed protective device is **requested from the utility**.
- **Why:** in a building, the apartment's TSG is switched off from the TP on the ground floor, several floors away: anyone can switch it back on, or the label may be wrong. That is why the 770 requires PIAs **lockable in the open position**: to fit the padlock.
- **How:** open the unit's switch in the collective meter cabinet, fit the DIN lockout device with your padlock and the tag; notify the person in charge or the building management; go up and verify with a tester at the TSG (between phase and neutral, phase and PE, neutral and PE) before touching anything; if you are also going to work on the TSG itself with its incoming device open, remember that the input terminals stay live until it is switched off downstairs. Detailed procedure in [site-safety.md](site-safety.md), ELEC-SEG-3 to ELEC-SEG-6.
- **Verify:** there is one padlock per person working; the key is held by the person working; the tester worked before and after the verification.
- **Don't:** work trusting the label on the ground floor; lock with insulating tape; break a utility seal "to switch off further up".
- **Source:** AEA 90364-7-770:2017, 770.16.5.2 (PIAs lockable in the open position); Decreto 911/96 art. 85 (minimum mandatory lockout: "Prohibido Maniobrar" (do not operate) sign with the name of the person in charge at the place of operation) and art. 86 (de-energize and check before working); Decreto 351/79 Anexo VI (lockout/tagout (LOTO), *consignación*); see ELEC-SEG-3 and ELEC-SEG-4.

## What this guide does not replace
- The **design**, the calculation and the **signature** are done by a professional or qualified installer with the competence required by the jurisdiction (AEA 90364-7-770, 770.2.1); the agent guides and reviews, it does not sign.
- The **utility** decides the service connection, the meter, the model of box and collective meter cabinet and their distances; the **municipality** and the regulatory body decide approval, inspection by the authority and inspections. See [regulations-and-permits.md](regulations-and-permits.md).
- The current AEA Reglamentación (wiring regulations) (and the Ed. 2026 of the 770 when it is published) and the manufacturer's data sheet of each device take precedence over this guide.
- No step of this guide authorizes live work; the checks marked "live" are only for trained and equipped personnel.
