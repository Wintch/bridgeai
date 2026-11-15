---
title: Conductors and conduits (cables, conduit, boxes, voltage drop, splices)
scope: choosing cables and wiring systems in low-voltage building installations in Argentina (houses, apartments, buildings, shops); minimum cross-sections, colors, current-carrying capacity, voltage drop, short circuit, conduit, boxes, cable trays, risers, underground and overhead runs, outdoor locations, splices, rewiring
when_to_use: choose which cable to buy and where it can go; size a cross-section or a conduit; check whether existing wiring complies; calculate the voltage drop of a sub-main or a circuit; plan the riser of a building; run the line from the meter pillar to the house; supply an air conditioner, an oven or an EV charger; rewire an old installation; decide how to splice
related: [README.md, regulations-and-permits.md, grades-and-circuits.md, protection.md, earthing.md, panels.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md]
as_of: 2026-11-15
sources:
  - "AEA 90364-7-770 Ed. 2017 (single-family houses up to 63 A); Ed. 2026 is already sold in digital form (print on pre-sale), with no published effective date; not reviewed here"
  - "AEA 90364-7-771 Ed. 2006 with Corrigendum 1 (2007) (dwellings, offices and single shops), current edition according to the AEA store"
  - "AEA 90364-7-772 Ed. 2019 (common areas and common services), 772.1.1"
  - "AEA 90364-5-52 (ch. 52, wiring systems) and IEC 60364-5-52 (annexes B and G)"
  - "Res. SIyC 236/2024 (Annex II in the text of Res. SIyC 26/2025, IF-2025-17295098-APN-DNRT#MEC: cables in items 4.3.1 to 4.3.10, conduit in 4.1.1 to 4.1.13) and Disp. DNRT 2/2025, Annex IF-2025-38164600-APN-DNRT#MEC; Res. SIyC 237/2024; Disp. DNRT 1/2024; argentina.gob.ar, service 'Marcado de conformidad' (conformity marking) (consulted 2026-11-15)"
  - "Res. SIyC 16/2025 (repeals Res. SC 169/2018)"
  - "Manufacturer datasheets (Prysmian Afumex Green, Ed. 2026)"
---
# Conductors and conduits

Rules for choosing, sizing and installing cables and wiring systems on site. Each rule has a stable ID (ELEC-CON-n) so the
agent, a review or a site report can cite it ("does not comply with ELEC-CON-12"). The values come from the AEA 90364
Reglamentación (wiring regulations) and from national resolutions, and each one carries its source. AEA and IRAM standards
are paid, so here they are summarized and the clause or table is cited. For the exact number in a project, open the standard.

**Which edition is used (as of 2026-11-15):**
- **AEA 90364-7-771, Ed. 2006** (dwellings, offices and single shops). The AEA store still offers it as the current edition, with corrigenda published at aea.org.ar.
- **AEA 90364-7-770** (single-family houses up to 63 A, prospective short-circuit current ≤ 10 kA, BA2 users and BD1 evacuation condition). The values in this guide come from the text of **Ed. 2017**. The AEA already sells **Ed. 2026** in digital form (the print edition is on pre-sale, with delivery announced from 2026-11-16) and has not published an effective date; we could not review its text: before citing a value in a new project, confirm it in Ed. 2026.
- **AEA 90364-7-772, Ed. 2019**: common areas and common services of buildings. According to its 772.1.1, the installations of each dwelling, office or shop in the building are governed by 770 or 771 "según corresponda" (as applicable), and the sub-main circuits that run up the riser shafts (*columnas montantes*) must also meet the requirements of 772.
- **AEA 90364-7-718, Ed. 2008**: places of public assembly.

**770 or 771 in an apartment.** 770 presents itself as the section for "viviendas unifamiliares" (single-family houses) and
does not say expressly whether it includes an apartment in a condominium building (*propiedad horizontal*). This guide follows
the criterion of [grades-and-circuits.md](grades-and-circuits.md) (ELEC-CIR-1): each apartment is designed with **771**, unless
the enforcing authority accepts 770 in writing. Where the two agree, 770 Ed. 2017 is cited. Where they differ, the table in
ELEC-CON-24 gives both values. In the riser of a building, always apply the stricter value.

**Calculations:** the agent does not calculate from memory. It uses the offline calculator `gateway electricidad ...` (current, voltage drop, cross-section, coordination) and shows the working.

## Quick reference

| Situation | Rules |
|---|---|
| Which cable to buy and whether it is legal to sell it | ELEC-CON-1, ELEC-CON-2 |
| Can I use flexible cord (*tipo taller*), twin flex (*paralelo*) or solid wire? | ELEC-CON-3 |
| Is halogen-free cable (LS0H) needed? | ELEC-CON-4 |
| Minimum cross-section of each line or circuit | ELEC-CON-5, ELEC-CON-6 |
| Colors of phase, neutral, PE and switch returns | ELEC-CON-7 |
| How much current can this cable carry? | ELEC-CON-8 |
| Voltage drop (long sub-main, riser, motor) | ELEC-CON-9 |
| Can I put several circuits in the same conduit? | ELEC-CON-10 |
| Which conduit to use (steel, rigid PVC, corrugated) | ELEC-CON-11 |
| Conduit diameter and fill | ELEC-CON-12 |
| Bends, junction boxes, distance between boxes | ELEC-CON-13 |
| Boxes: size, knockouts, accessibility | ELEC-CON-14 |
| Embedding in masonry or concrete | ELEC-CON-15 |
| Surface conduit or conduit above a suspended ceiling | ELEC-CON-16 |
| Cable trays | ELEC-CON-17 |
| Data, TV, door entry or alarm next to 220 V | ELEC-CON-18 |
| Buried run (yard, garage), crossings with other services | ELEC-CON-19 |
| Pulling cables: pulling force, spare length, vertical runs, conductors in parallel | ELEC-CON-20 |
| Splices and branch connections | ELEC-CON-21 |
| Joining aluminum to copper | ELEC-CON-22 |
| Riser of a building (meter panel to apartments) | ELEC-CON-23, ELEC-CON-25 |
| 770 or 771? Which values change | ELEC-CON-24 |
| Fire-stop sealing of penetrations between floors and shafts | ELEC-CON-25 |
| Can the cable withstand the short circuit? | ELEC-CON-26 |
| Line from the meter pillar (*pilar*) to the house (buried or overhead) | ELEC-CON-27 |
| Cable for a split air conditioner | ELEC-CON-28 |
| Outdoor locations, terraces, garages, damp locations | ELEC-CON-29 |
| Water heater, oven, cooktop, EV charger | ELEC-CON-30 |
| Rewiring an old installation (no PE, cloth- or rubber-insulated cable) | ELEC-CON-31 |

## Cable types

| Standard | What it is | Where it goes | Where it does NOT go |
|---|---|---|---|
| IRAM NM 247-3 (in practice replaced IRAM 2183) | Single-core cable without sheath, PVC insulation, 450/750 V, 70 °C in service | Inside conduit (embedded or surface) or surface trunking | Directly in a wall, above a ceiling, in a cable tray, buried (except as PE: ELEC-CON-17) |
| IRAM 62267 | Same as the previous one but LS0H (low smoke, halogen-free), 450/750 V | Same as NM 247-3. Mandatory where table 771.12.I requires it (ELEC-CON-4) | Same as NM 247-3 |
| IRAM 2178-1 (formerly IRAM 2178) | Sheathed cable (*vaina*), 0.6/1 kV, single-core or multicore | Conduit, cable tray, direct burial or in a duct, "U"-shaped conduit runs, entry into panels with cable glands | — |
| IRAM 62266 | Same as 2178-1 but LS0H, 1 kV | Same as 2178-1 where LS0H is required | — |
| IRAM NM 247-5 (in practice replaced IRAM 2158), flexible cord (*tipo taller*) | Sheathed flexible cord, 300/500 V | Supplying mobile or portable appliances (extension cords, machines) | **Fixed installation: prohibited** |
| IRAM 2263 | Aluminum XLPE aerial bundled cable (overhead lines) | Overhead service drop (defined by the utility); outdoor overhead distribution | Inside the dwelling |

Sources: AEA 90364-7-770 Ed. 2017, 770.10.1, 770.10.2 and normative references; AEA 90364-7-771 Ed. 2006, 771.12.1,
notes 2 and 5, and table 771.16.I, note 2. According to the AEA, NM 247-3 and NM 247-5 replaced IRAM 2183 and 2158 "en la
práctica" (in practice), "aun cuando ambas normas no son estrictamente equivalentes" (even though the two standards are not
strictly equivalent).

### ELEC-CON-1: Only certified, flame-retardant cables rated 450/750 V or more
- **Rule:** in fixed installations use only flame-retardant (non-flame-propagating) cables, with a rated voltage of 450/750 V or more, and with current conformity marking. Every wiring system must be flame-retardant.
- **Why:** a counterfeit cable (real cross-section smaller than the printed one, copper with impurities, PVC that propagates flame) overheats with currents that the protection lets through, and it is the classic cause of fire in an installation that "was correctly calculated".
- **How:**
  1. Check that the cable has printed along its length the standard (IRAM NM 247-3, 62267, 2178-1 or 62266), the cross-section, the voltage and the manufacturer.
  2. Check that the reel has the conformity marking: the new mark with a QR code, which leads to the sworn declaration and the certificate, or the previous mark on old stock.
  3. Buy from a distributor who can show you the sworn declaration of conformity: they are required to have it.
- **Verify:**
  - Scan the QR code on the reel and check that it leads to a current certificate for that standard and that manufacturer.
  - If you doubt the cross-section, don't measure the diameter of the strand bundle: in a class 5 flexible cable the strands deform and the measurement misleads. Weigh 1 m of stripped conductor: copper weighs about 8.9 g per mm² per meter, so a 2.5 mm² conductor is around 22 g/m. Another option: measure the resistance of the reel and compare it with IRAM NM 280 / IEC 60228 (2.5 mm² class 5: 7.98 Ω/km maximum at 20 °C). For 100 m that is less than 0.8 Ω, so you need a micro-ohmmeter or a four-wire method.
- **Don't:** buy unbranded cable or cable "por kilo" (by the kilo); accept cable that does not state the standard; use telephone, UTP or alarm cable for 220 V.
- **Source:**
  - Cable requirements: AEA 90364-7-770 Ed. 2017, 770.10. Flame retardance is tested according to IRAM-NM IEC 60332-1.
  - National regime: Res. SIyC 236/2024 (2024-08-29), Annex II (materials for electrical installations) in the text set by Res. SIyC 26/2025 (BO 2025-02-25; item numbering in [iram-standards.md](iram-standards.md) ELEC-IRA-2), and Disp. DNRT 2/2025, Annex IF-2025-38164600-APN-DNRT#MEC. Point 5.2.3 limits cables (fixed indoor, cords, and power, control and signaling cables) to certification schemes 1b or 5. Point 5.3 requires marking according to Res. SIyC 237/2024 (sec. 3.3) and Disp. DNRT 1/2024 (sec. 3.4). See also ELEC-NOR-14 in [regulations-and-permits.md](regulations-and-permits.md).
  - Dates: argentina.gob.ar, service "Marcado de conformidad" (conformity marking) (consulted 2026-11-15). Since 2025-10-01 no certified product may be sold without identification, either the previous mark or the new one. Products manufactured or imported after that date carry the new marking, and earlier stock is proven with a purchase invoice or import documents. The extension to 2026-10-01 (Res. SIyC 313/2025 and 428/2025) applies only to toys sold with food or in contact with it: **it does not cover cables**.
  - Res. SC 169/2018 is repealed by Res. SIyC 16/2025, art. 8 (BO 2025-02-25).
  - Resistance from IEC 60228 / IRAM NM 280 (7.98 Ω/km): **Not verified in a primary source** in this review. It is the widely published table value; confirm it in the manufacturer's datasheet.

### ELEC-CON-2: Each cable type goes in the wiring system that suits it
- **Rule:**
  - Single-core cables without sheath (IRAM NM 247-3, IRAM 62267) go **always** inside conduit or a surface trunking system.
  - Sheathed cables (IRAM 2178-1, IRAM 62266) can go in conduit or surface trunking, in a cable tray, directly buried or in a buried duct.
- **Why:** the insulation of an unsheathed single-core cable is a single layer designed to be protected by the conduit. Exposed to impacts, UV rays, moisture or rodents it gets damaged, and an insulation fault in an accessible place is an electric shock.
- **How:** for each run, ask yourself where the cable goes: conduit, cable tray, ground, or a section that leaves the conduit toward a panel or a piece of equipment. If the cable is outside a conduit or surface trunking at any point, it must be sheathed. "U"-shaped conduit runs that collect water (crossings under the floor on the ground floor and basement) also take sheathed cable, because water accumulates inside. A sheathed cable enters a box or panel through a cable gland, and the conduit it comes out of ends in a threaded bushing.
- **Verify:** walk the installation looking for exposed single-core cables between the conduit and the panel, at the entry to air conditioning units and on the drops to pumps or gates.
- **Don't:** "stretch" a single-core cable from the last box to the equipment without conduit; lay single-core cables in a cable tray; bury single-core cables inside a hose.
- **Source:** AEA 90364-7-770 Ed. 2017: 770.10.2 a) and b) (permitted cables), 770.10.3.6.3 ("U"-shaped conduit runs) and 770.10.5.1 (entry into boxes and panels). AEA 90364-7-771 Ed. 2006, table 771.12.I.

### ELEC-CON-3: What is not used in fixed installations
- **Rule:** the following are prohibited in fixed installations:
  - flexible cords (*tipo taller*) and IRAM NM 247-5 cables (including twin flex, *paralelo*), IRAM 2039 and IRAM 2188;
  - **solid-conductor cables** (a single wire);
  - cables embedded directly in a wall, ceiling or floor, without conduit;
  - unsheathed single-core cables fixed on masonry or plaster;
  - sheathed cables fixed on masonry below 2.5 m;
  - loose cables above a suspended ceiling;
  - unsheathed single-core cables inside hollow partitions or ceilings;
  - cables on or under wooden or combustible channels, battens or skirting boards;
  - bare conductors (except as an earth electrode or as PE in a cable tray: ELEC-CON-17);
  - orange conduit or any flame-propagating conduit.
- **Why:**
  - 300/500 V cord is for appliances that are plugged and unplugged. In a wall it has no mechanical protection, is often spliced and does not have the cross-section it claims.
  - Solid wire fatigues and breaks at terminals and splices.
  - Orange (flame-propagating) conduit carries fire from one box to the next.
- **How:** if you inherit an installation with flexible cord "de pared a pared" (wall to wall), rigid wire or orange conduit, it is a run to redo, not to patch (ELEC-CON-31). Cut the supply before touching anything (see [site-safety.md](site-safety.md)).
- **Verify:** with the circuit switched off and verified dead, open the boxes and look at the printing on the cable: "NM 247-5", "300/500 V", "2158" or "taller" indicates a cord. Bend the end: if it is a single wire, it is solid.
- **Don't:** use flexible cord "porque es más grueso y más seguro" (because it is thicker and safer); use twin flex for a lighting circuit; embed orange "de plomería" (plumbing) corrugated conduit.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.10.1 a) to l). AEA 90364-7-771 Ed. 2006, 771.12.1 (same list; note 4: flexible cords "no son aptos para instalaciones eléctricas fijas" (are not suitable for fixed electrical installations)).

### ELEC-CON-4: LS0H cables and wiring systems where table 771.12.I requires them
- **Rule:** use low-smoke, halogen-free cables (LS0H: IRAM 62267 for single-core, IRAM 62266 for sheathed), and wiring systems that meet the same, when **any** of these conditions applies (column 1 of table 771.12.I):
  - emergency evacuation **BD2, BD3 or BD4** (difficult evacuation or many people: tall buildings, basements, cinemas, theaters, shopping malls, hospitals);
  - capability of persons **BA2 in premises** (kindergartens, daycare centers) or **BA3** (people who cannot look after themselves, as in nursing homes). BA2 in dwellings does not trigger it;
  - building design **CB2** (risk of fire spread, for example by chimney effect in tall buildings);
  - places of public assembly (AEA 90364-7-718).

  In risers and escape routes of an apartment building they are recommended even if none of those conditions applies (see ELEC-EDI-9 in [buildings.md](buildings.md)).
- **Why:** in a fire, PVC gives off dense black smoke and hydrochloric acid. Most fire victims die from the smoke, not the flames. A cable that "no propague la llama" (does not propagate flame) does not guarantee that people can evacuate.
- **How:**
  1. Define the external influences with the designer: BA (capability of persons), BD (evacuation conditions) and CB (building design). See [regulations-and-permits.md](regulations-and-permits.md).
  2. If it falls in column 1, use LS0H in the whole fixed installation. If there is BD2, BD3 or BD4 you are already outside 770 and 771 applies.
  3. Insulating wiring systems **on the surface** (conduit, surface trunking, ducts) must also be fire-retardant, low smoke and halogen-free (note 2 of table 771.12.I).
  4. The current-carrying capacity of thermoplastic LS0H is the same as that of PVC: the AEA tables put them in the same column.
- **Verify:** the printing on the cable says "IRAM 62267" or "IRAM 62266" and "LS0H" (or "libre de halógenos"); the surface conduit or trunking declares itself halogen-free.
- **Don't:** assume that "no propagante" (flame-retardant) equals "libre de halógenos" (halogen-free): they are different tests.
- **Source:**
  - AEA 90364-7-771 Ed. 2006, table 771.12.I, column 1 (BD2, BD3, BD4; BA2 in premises and BA3; CB2 → IRAM 62267 / 62266 cables and halogen-free wiring systems) and note 2. Column 2 corresponds to BD1, BA1, BA2 in dwellings, BA4, BA5 and CB1.
  - Scope of 770 (BA2 and BD1) and referral to 771: AEA 90364-7-770 Ed. 2017, 770.1 and general considerations.
  - **Not verified in a primary source:** the text of AEA 90364-7-718 (2008) that requires LS0H, and from what height a residential building moves to BD2 or CB2. A building with ground floor plus 4 floors is usually treated as BD1, but the designer decides, and the municipality or fire department may require more.
  - Prysmian (Afumex Green datasheet Ed. 2026) recommends its IRAM 62267 cables for "alta densidad de ocupación y/o con condiciones de evacuación difíciles" (high occupancy density and/or difficult evacuation conditions).
## Minimum cross-sections

### ELEC-CON-5: Respect the minimum cross-sections even if the calculation gives less
- **Rule:** the cross-section is calculated by current-carrying capacity (ELEC-CON-8) and voltage drop (ELEC-CON-9), and checked against short circuit (ELEC-CON-26). It can never be below these minimums:

| Line or circuit | 770 Ed. 2017 (copper) | 771 Ed. 2006 (copper) |
|---|---|---|
| Main line (meter to main panel) | 4 mm² | 4 mm² |
| Sub-main circuit (panel to panel) | 2.5 mm² | 2.5 mm² |
| General-purpose lighting final circuit (IUG) | 1.5 mm² | 1.5 mm² |
| General-purpose socket outlet final circuit (TUG) | 2.5 mm² | 2.5 mm² |
| IUG circuit that includes socket outlets | 2.5 mm² | 2.5 mm² |
| Special-use circuits (IUE, TUE) | 2.5 mm² | 2.5 mm² |
| Specific-use circuit (except MBTF) | 2.5 mm² | 2.5 mm² |
| Specific-use circuit supplying MBTF | 1.5 mm² | 1.5 mm² |
| **Feed and return of switches (*llaves de luz*, light switches)** | **1 mm²** | **1.5 mm²** |
| Protective conductor (PE) | 2.5 mm² | 2.5 mm² |
| Control without power transmission (home automation) | 0.5 mm² | no row of its own |

- **Why:** the minimums cover mechanical strength during pulling, short circuit and future extensions. With 1.5 mm² on socket outlets, the first heater that gets plugged in overheats the circuit.
- **How:** calculate the cross-section, compare it with the table and keep the larger one. In an apartment designed under 771, the switch returns go in **1.5 mm²**: the 1 mm² of 770 does not comply. In site practice people usually standardize: 2.5 mm² for every final circuit and PE, so as not to mix up reels.
- **Verify:** in each box, the cross-section printed on the cable matches the one in the technical report for that circuit.
- **Don't:** wire socket outlets in 1.5 mm²; use 1.5 mm² as PE; run the main line in 2.5 mm²; use 1 mm² returns in an installation that falls under 771.
- **Source:** AEA 90364-7-770 Ed. 2017, table 770.11.I. AEA 90364-7-771 Ed. 2006, 771.13 and table 771.13.I. Corrigendum 1 (2007) of 771 does not modify that table.

### ELEC-CON-6: The PE runs through the whole installation with the correct cross-section
- **Rule:** the protective conductor is insulated copper (IRAM NM 247-3, 2178-1, 62266 or 62267), green-yellow, and reaches **all** boxes and outlet points (*bocas*), even those without a socket outlet. Its cross-section, and also that of the earthing conductor, comes from the same table:
  - if the phase S is up to 16 mm²: equal to S;
  - if S is more than 16 and up to 35 mm²: 16 mm²;
  - if S is greater than 35 mm²: S/2.

  Absolute minimums: 2.5 mm² for the PE and **4 mm²** for the earthing conductor (from the earth electrode to the main busbar). The earthing conductor is run **independently of the PE**, even if they share a wiring system. Example: if the line is 10 mm², the earthing conductor is 10 mm², not 4.
- **Why:** without a continuous PE there is no protection against indirect contact. The RCD (*disyuntor* / *diferencial*) needs a path to earth to "see" the leakage (see [earthing.md](earthing.md)).
- **How:** the PE travels in the same conduit as the live conductors of its circuit (ELEC-CON-10). It is recommended not to cut it except in panels, for a change of cross-section, and at splices. Metal boxes and conduit are connected by branching from the PE, without interrupting it. The 4 mm² minimum for the earthing conductor assumes an insulated cable protected inside conduit. If the run is buried or without mechanical protection, follow [earthing.md](earthing.md) (ELEC-PAT-6).
- **Verify:** PE continuity measurement between the earth bar and each earth terminal (see [testing-and-commissioning.md](testing-and-commissioning.md)); cross-section of the earthing conductor ≥ the one the table gives for the phase of the main line.
- **Don't:**
  - use the metal conduit as PE;
  - bypass (*puentear*) earth to neutral at the socket outlet;
  - use a cable of another color as PE "porque no quedaba verde-amarillo" (because there was no green-yellow left);
  - share a PE between lines from different meters (ELEC-CON-25).
- **Source:**
  - AEA 90364-7-770 Ed. 2017: 770.14.4.5 (PE) and table 770.14.I. The table covers the cross-section of the PE and of the PAT (earthing) conductor ("En ningún caso la sección del cable de puesta a tierra debe ser menor que 4 mm². Este cable se debe tender en forma independiente al conductor de protección…" (In no case shall the cross-section of the earthing conductor be less than 4 mm². This cable shall be run independently of the protective conductor…)). Also 770.10.3.2: metal wiring systems do not replace the PE.
  - **Not verified in a primary source:** IEC 60364-5-54, table 54.1, for the buried earthing conductor: 16 mm² copper if it has corrosion protection but no mechanical protection, 25 mm² if it has neither. These are values from prior knowledge and could not be consulted.

## Colors

### ELEC-CON-7: Identification colors
- **Rule:**

| Function | Designation | Color |
|---|---|---|
| Phase L1 (R) | L1 | Brown (*castaño* / *marrón*) |
| Phase L2 (S) | L2 | Black |
| Phase L3 (T) | L3 | Red |
| Neutral | N | Light blue (*celeste*); blue is also accepted |
| Protective conductor | PE | Green-yellow (two-color) |

  - In a single-phase installation the phase can be any of the three phase colors. If the single-phase circuit comes from a three-phase supply, it must have the color of the phase it comes from.
  - Green-yellow is **only** for PE. Plain green and plain yellow are **prohibited** for any function.
  - Light blue or blue is only for neutral.
  - Returns of light switches and other functions do not go in phase, neutral or PE colors, nor in plain green or yellow. Use another color, for example white or gray.
- **Why:** color is the first barrier against human error. Whoever opens a box years later must be able to tell what each cable is without measuring.
- **How:** if, by force majeure, you use another color for a phase or a return (never light blue, blue, green, yellow or green-yellow), identify the cable at both ends of each run with tape of the standard color, rings or indelible marker.
- **Verify:** in each box, the earth terminal of the socket outlet receives green-yellow, the neutral receives light blue and the switch breaks the phase, not the neutral.
- **Don't:** use green-yellow as phase or return; use light blue as phase; "paint" a cable with tape to change its function when cable of the correct color is available.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.10.3.8.5 and table 770.10.XIII.

## Current-carrying capacity

### ELEC-CON-8: Current-carrying capacity depends on installation method, temperature and grouping
- **Rule:** the circuit design current (IB) must be less than or equal to the corrected current-carrying capacity of the cable (Iz). The protection is chosen between the two: IB ≤ In ≤ Iz (see [protection.md](protection.md)). Iz is calculated like this:

  Iz = I(table) × Ft (temperature) × Fa (grouping)

- **Why:** PVC withstands 70 °C in continuous service (160 °C in short circuit). Above that the insulation ages fast, softens and ends in a fault.
- **How:**
  1. **Installation method.** The AEA tables are organized by method (IEC 60364-5-52 nomenclature):
     - B1: single-core cables in embedded or surface conduit;
     - B2: multicore cable in conduit;
     - D1: in a buried duct;
     - D2: directly buried.
  2. **Reference temperature.** The AEA 770/771 tables are at **40 °C** air (the temperature of the ENRE region) and 25 °C soil for buried cables, with a soil thermal resistivity of 1 K·m/W. In other regions use the temperature from IRAM 11603 or the one set by the local authority.
  3. **Temperature correction** (PVC, 40 °C base): see the table below.
  4. **Grouping correction** (several circuits in the same wiring system, or several conduits in contact): see the table below.
  5. The PE does not count as a loaded conductor.
- **Verify:** in the technical report, each circuit shows method, I(table), Ft, Fa, Iz and In.
- **Don't:** use catalog tables at 30 °C without correcting to 40 °C; protect a 1.5 mm² cable with a 16 A MCB (*térmica*) (Iz = 15 A < 16 A); ignore grouping when there are three circuits in the same conduit or many conduits packed together in a riser (*montante*).
- **Source:**
  - AEA 90364-7-770 Ed. 2017: 770.12.1, 770.12.2.1, table 770.12.I (current-carrying capacity), table 770.12.II (grouping, based on table B52-17 of AEA 90364-5-52) and table 770.12.III (sheathed cables).
  - AEA 90364-7-771 Ed. 2006: table 771.16.I, with the same values as 770.12.I; table 771.16.II.a (temperature, based on B52-14); table 771.16.II.b (0.80 for 2 circuits and 0.70 for 3, same as 770.12.II); table 771.16.IV (grouping of more circuits, same as B52-17).

**Indicative values: single-core PVC or LS0H cables (IRAM NM 247-3 / 62267), copper, in embedded or surface conduit (method B1), 2 loaded conductors + PE (single-phase), 40 °C ambient**

| Cross-section | 1.5 mm² | 2.5 mm² | 4 mm² | 6 mm² | 10 mm² | 16 mm² | 25 mm² | 35 mm² |
|---|---|---|---|---|---|---|---|---|
| Current-carrying capacity | 15 A | 21 A | 28 A | 36 A | 50 A | 66 A | 88 A | 109 A |

Source: AEA 90364-7-770 Ed. 2017, table 770.12.I, column "2x", and AEA 90364-7-771 Ed. 2006, table 771.16.I (same values). They match IEC 60364-5-52 method B1 at 30 °C multiplied by 0.87.

> **Warning:** these are values for **a single circuit** in the conduit, at 40 °C. With more circuits or higher temperature (near a water heater, in a hot roof space, under metal sheeting) Iz goes down. For three-phase (3 loaded) the column is different (for example 2.5 mm² → 18 A, 10 mm² → 44 A): see table 770.12.I or 771.16.I. For sheathed cables, buried or in a cable tray, use table 770.12.III, 771.16.III or AEA 90364-5-52.

**Temperature factor Ft, PVC insulation (70 °C), 40 °C base**

| Ambient | 25 °C | 30 °C | 35 °C | 40 °C | 45 °C | 50 °C | 55 °C | 60 °C |
|---|---|---|---|---|---|---|---|---|
| Ft | 1.22 | 1.15 | 1.08 | 1.00 | 0.91 | 0.82 | 0.70 | 0.57 |

Source: AEA 90364-7-771 Ed. 2006, table 771.16.II.a, based on table B52-14. The formula Ft = √((70 − θ) / (70 − 40)) approximates the table within ±0.01 (at 55 °C it gives 0.71). For the calculation, use the table.

**Grouping factor Fa (circuits grouped in the same wiring system, or conduits in contact)**

| Circuits | 1 | 2 | 3 | 4 | 5 | 6 | 8 |
|---|---|---|---|---|---|---|---|
| Fa, bunched, embedded or enclosed (item 1) | 1.00 | 0.80 | 0.70 | 0.65 | 0.60 | 0.57 | 0.52 |
| Fa, single layer on wall or floor (item 2) | 1.00 | 0.85 | 0.79 | 0.75 | 0.73 | 0.72 | 0.71 |

Source: the values for 2 and 3 circuits in a conduit are those of tables 770.12.II and 771.16.II.b. The rest comes from AEA
90364-7-771 Ed. 2006, table 771.16.IV (same as B52-17), items 1 and 2. According to its note 2, if the spacing between
adjacent cables exceeds twice their outer diameter, no reduction is needed. In dwellings no more than 3 circuits per conduit
are allowed (ELEC-CON-10). The row for 8 is for the conduits of a riser (ELEC-CON-23).

**Worked example.** Three general-purpose socket outlet circuits (TUG) in 2.5 mm² share an embedded conduit in a room at 40 °C.
- **First, can they be grouped?** With 16 A MCBs: 3 × 16 A = 48 A > 36 A. The AEA does not allow those three circuits in the same conduit (ELEC-CON-10), so the Iz calculation is not even needed.
- If they were grouped anyway, by calculation: Iz = 21 A × 1.00 × 0.70 = 14.7 A, and a 16 A MCB would not protect the cable either (16 A > 14.7 A).
- **Options that do comply:**
  - two 16 A circuits (32 A ≤ 36 A): Iz = 21 A × 0.80 = 16.8 A ≥ 16 A;
  - three 10 A circuits (30 A ≤ 36 A): Iz = 14.7 A ≥ 10 A;
  - 16 + 10 + 10 A (36 A): the 16 A one does not pass with Fa 0.70 (14.7 A < 16 A), so it must be moved to another conduit;
  - the typical case of three lighting circuits (IUG) in 1.5 mm² with 10 A MCBs: 15 A × 0.70 = 10.5 A ≥ 10 A, complies.

## Voltage drop

### ELEC-CON-9: Check the voltage drop: 3 % on lighting and socket outlets, 5 % / 15 % on motors, 1 % on sub-mains
- **Rule:** the voltage drop between the output terminals of the main panel and any point of use cannot exceed:
  - **3 %** on general-purpose or special-use final circuits (lighting and socket outlets);
  - **5 % in steady state and 15 % during starting** on circuits that supply only motors.

  On **sub-main circuits**:
  - **770 Ed. 2017:** it is **recommended** not to exceed 1 %;
  - **771 Ed. 2006:** the 1 % is **mandatory** ("en ningún caso… deberá exceder del 1 %" (in no case… shall it exceed 1 %)). Therefore, measured from the sub-panel (TS, *tablero seccional*), the final circuit is limited to **2 %** (to **4 %** if it supplies motors).

  The total drop of a final circuit is the sum of the drop of the final circuit and that of the sub-main that feeds its panel.
- **Why:** with low voltage, motors (pumps, refrigerators, compressors) draw more current and burn out; power supplies and LEDs fail; and a large drop gives away a cable that is heating up.
- **How:**
  - **General formula** (AEA): ΔU = k × I × L × (R cos φ + X sin φ), with:
    - k = 2 for single-phase, √3 ≈ 1.732 for three-phase (ΔU between phases);
    - I: line current, in A;
    - L: length of the run (distance between the two points, not meters of cable), in km;
    - R and X: resistance and reactance of the conductor, in Ω/km.

    Without data: cos φ = 0.85 (sin φ = 0.53), and for motor starting cos φ = 0.30.
  - **Simplified formula for small cables** (up to about 25 mm², where X matters little): R = ρ / S.
    - ρ of copper at operating temperature: 0.0225 Ω·mm²/m (at 20 °C it is 0.0178).
    - ρ of aluminum at operating temperature: 0.036 Ω·mm²/m (at 20 °C it is 0.0282).
    - Single-phase: ΔU = 2 × L × I × ρ × cos φ / S, with L in m and S in mm².
    - Three-phase: ΔU = √3 × L × I × ρ × cos φ / S.
    - As a percentage: ΔU% = ΔU / U × 100, with U = 220 V for single-phase and 380 V between phases for three-phase.
  - **AEA quick table** (single-phase, single-core cables in conduit, cos φ = 0.8), in V per A per km:

| Cross-section | 1.5 | 2.5 | 4 | 6 | 10 | 16 | 25 | 35 mm² |
|---|---|---|---|---|---|---|---|---|
| Drop | 26 | 15 | 10 | 6.5 | 3.8 | 2.4 | 1.6 | 1.2 V/(A·km) |

  - The table is at cos φ = 0.8 and the formula uses the default value of 0.85, so they give slightly different results. Either one works for checking, but don't mix them within the same calculation.
  - For the calculation, lighting and socket outlet circuits are taken with their maximum simultaneous demand at the farthest end. For lighting, 2/3 of the load is taken at the end.
- **Verify:** the technical report shows ΔU% of the sub-main and of each long final circuit. In a finished installation, measure the no-load voltage and the voltage with a known load at the farthest outlet point: the difference is the real drop.
- **Don't:** size the riser of a building only by current-carrying capacity; use the meters of cable (out and back) as L in the formula with k = 2, because you would count the length twice; accept a sub-main at 1.4 % in an apartment designed under 771.
- **Source:**
  - AEA 90364-7-770 Ed. 2017, 770.15.6 (limits, method and note "se recomienda… 1 %" (1 % is recommended)) and table 770.15.IV.
  - AEA 90364-7-771 Ed. 2006, 771.13 b): same limits of 3 % and 5 % / 15 %. Its note sets the mandatory 1 % on sub-mains and the 2 % / 4 % for the final circuit from the sub-panel.
  - ρ at operating temperature: IEC 60364-5-52, annex G (ρ = 1.25 × ρ20).
  - **Not verified in a primary source:** a specific limit for the main line, from the meter to the main panel. The AEA measures from the output terminals of the main panel, and what happens upstream is set by the utility (AEA 95150).

**Worked example, single-phase (4-story building).** The main panel of each apartment is next to the meter, on the ground
floor (ELEC-CON-23), so the line that goes up is a sub-main. L = 20 m to the panel of the apartment on the 4th floor.

Assumed demand: apartment of Medium electrification grade with a maximum simultaneous power demand of about 4 kVA plus a 1.5 kVA air
conditioner, that is 5.5 kVA → I = 5500 VA / 220 V = **25 A**. Where the demand comes from and how the grade is determined: see
[grades-and-circuits.md](grades-and-circuits.md). There, Example A (58 m²) gives 4.4 kVA, and
[buildings.md](buildings.md) uses about 7 kVA per apartment (*depto*) (High grade with a TUE for the AC: 6952 VA in [examples/README.md](examples/README.md)).
- With 6 mm²: ΔU = 2 × 20 × 25 × 0.0225 × 0.85 / 6 = 3.19 V → 1.45 %. With the table (cos φ 0.8): 6.5 × 25 × 0.020 = 3.25 V → 1.48 %. **It exceeds 1 %**: it does not comply under 771 and is not advisable under 770. Try the next cross-section.
- With 10 mm²: with the table, ΔU = 3.8 × 25 × 0.020 = 1.90 V → **0.86 %** (with the formula it gives 1.91 V, 0.87 %). It complies with 1 %.
- Socket outlet final circuit in 2.5 mm², 15 m to the last outlet point, 10 A: with the table, ΔU = 15 × 10 × 0.015 = 2.25 V → 1.02 %. It complies with the 2 % from the sub-panel that 771 requires.
- **Total at the last socket outlet:** 0.86 % + 1.02 % = 1.88 % ≤ 3 %. Complies.
- **If the demand were 7 kVA** (31.8 A): with 10 mm² it gives 3.8 × 31.8 × 0.020 = 2.42 V → 1.10 %, which exceeds 1 %. With 16 mm² it gives 2.4 × 31.8 × 0.020 = 1.53 V → 0.69 %, and it complies.
- The protection and the grouping of the conduits in the riser still need checking: see ELEC-CON-23, step 3.

**Worked example, three-phase.** The common services of the building can have a three-phase supply even if the
apartments are single-phase (see [buildings.md](buildings.md)). Water lift pump on the roof terrace: 1.5 kW
three-phase, I ≈ 3.5 A from the nameplate (assumed figure: with cos φ 0.82 and efficiency 0.80, I = 1500 / (1.732 × 380 × 0.82 × 0.80)
= 3.47 A). L = 40 m from the common services panel, 2.5 mm² in conduit. R = 0.0225 / 2.5 = 9.0 Ω/km; X ≈ 0.08 Ω/km
(indicative for single-core cables in contact).
- In steady state: ΔU = 1.732 × 3.5 × 0.040 × (9.0 × 0.85 + 0.08 × 0.53) = 0.2425 × 7.692 = 1.87 V → 0.49 %. It complies with 5 %.
- At direct-on-line starting, with 6 × In = 21 A and cos φ = 0.30: ΔU = 1.732 × 21 × 0.040 × (9.0 × 0.30 + 0.08 × 0.95) = 1.455 × 2.776 = 4.04 V → 1.06 %. It complies with 15 %.
- Current-carrying capacity: 2.5 mm² with 3 loaded conductors = 18 A (table 770.12.I / 771.16.I), well above 3.5 A. The motor protection is provided by a motor protection circuit breaker (*guardamotor*) (see [special-installations.md](special-installations.md)).
## Grouping and conduit

### ELEC-CON-10: What can share a conduit
- **Rule:**
  - All the conductors of a circuit, **including the PE**, go in the same wiring system.
  - Each main line goes in its own conduit (*caño*).
  - Sub-mains of single-core cables (NM 247-3 / 62267) go in separate conduits. Up to three sub-mains in the same conduit are allowed only if they are sheathed cable (2178-1 / 62266) and from the same meter.
  - **In a cable tray** (771): main lines and sub-mains in sheathed cable can go without the limit of three (ELEC-CON-17).
  - General-purpose, special-use and specific-use circuits go in separate conduits. Exception: up to **3 general-purpose circuits** in the same conduit, if all three conditions are met:
    - they are on the same phase and from the same panel;
    - the sum of the In of their protective devices does not exceed 36 A;
    - together they supply no more than 15 outlet points (*bocas*).
  - Each outlet point serves a single circuit. It can be used as a junction box (*caja de paso*) for another circuit, but not as a branch box (*caja de derivación*).
- **Why:** separating circuits limits mutual heating (ELEC-CON-8) and prevents a short circuit in one from damaging the others. It also prevents someone from switching off "their" MCB (*térmica*) and finding voltage from another circuit in the same box.
- **How:** where different circuits share a run, identify each cable (colors, numbered rings) in all boxes. A surface trunking (*cablecanal*) with fixed dividers counts as separate wiring systems.
- **Verify:** with the circuits switched off and verified dead ([site-safety.md](site-safety.md)), open the junction boxes. The cables of each circuit must be identified and there cannot be cables from two different meters in the same conduit.
- **Don't:** run an air conditioning circuit (special use) through the socket outlet conduit; run the phase through one conduit and the neutral through another (induction and heating in metal conduit).
- **Source:** AEA 90364-7-770 Ed. 2017, 770.10.3.8.2 a) to g). AEA 90364-7-771 Ed. 2006, 771.12.3.13.2 a) to g), with the notes to b) and c) on cable trays.

### ELEC-CON-11: Which conduit to use depending on where it goes
- **Rule:**

| Situation | Permitted conduit |
|---|---|
| Construction with combustible materials (wood, etc.) | Heavy steel (IRAM-IAS U 500 2100) or semi-heavy steel (IRAM-IAS U 500 2005), threaded couplings, IRAM 62005 boxes. Exception: insulating conduit with AFDD on the final circuits |
| Embedded in cast concrete or chased into masonry ("obra húmeda", wet construction) | Heavy or semi-heavy steel; light steel (IRAM-IAS U 500 2224) with mechanical protection (ELEC-CON-15); flame-retardant insulating material: rigid IRAM 62386-21, pliable or corrugated IRAM 62386-22, flexible IRAM 62386-23. Minimum requirements of table 770.10.I: compression 750 N and temperature up to 90 °C if the concrete contains a setting accelerator |
| Dry construction (precast, boards) | The same, with the minimum requirements of table 770.10.II. Between inaccessible double partitions rigid conduit is recommended |
| Surface-mounted indoors | Steel (including stainless and galvanized or enameled light steel), classified flexible metal conduit, insulating conduit of "fuerte" (heavy) classification (compression 1250 N, impact 2 kg from 0.3 m), IRAM 62084 surface trunking, metal or insulating |
| Buried | IRAM 62386-24 conduit (or IRAM 13350 PVC with mechanical protection) (ELEC-CON-19) |
| Prohibited in all cases | Orange conduit or any flame-propagating conduit (IRAM 62386-1, clause 7.3) |

- **Why:** the conduit is the cable's mechanical and fire protection. It must withstand the concrete pour, being walked on in the slab and setting temperatures.
- **How:**
  - **Corrugated or "enrollable" (coilable) conduit** (pliable or pliable self-recovering): allowed **only embedded** in walls and slabs, and only if these conditions are met:
    - inspection of the run before covering (770.2.2);
    - orthogonal routing;
    - maximum 3 bends between boxes;
    - fixing at no more than 1 m (in a slab, tied to the reinforcement);
    - minimum bending radii;
    - fittings from the same system;
    - diameter according to the corrugated conduit table (ELEC-CON-12).

    It is not used suspended or resting on a suspended ceiling.
  - **Changes of system** (for example, from steel to PVC): always in a box or enclosure.
  - **Metal conduit:** it is earthed, and continuity is ensured by construction or with bonding jumpers.
- **Verify:** before the concrete pour or the plaster, inspect the run (photos with a tape measure). Ask for the IRAM 62386 mark or the classification printed on the conduit.
- **Don't:** use water or drain pipe "porque es más barato" (because it is cheaper); leave corrugated conduit in loops and unfixed bends; leave corrugated conduit hanging in a roof space.
- **Source:** AEA 90364-7-770 Ed. 2017: 770.10.1 l), 770.10.3.1 to 770.10.3.4 and tables 770.10.I and 770.10.II. According to the foreword of 771 Ed. 2006, that edition already incorporated pliable or flexible synthetic conduit "cumpliendo estrictas reglas de instalación" (following strict installation rules) (771.12.3.3.4).

### ELEC-CON-12: Minimum diameter and fill of the conduit
- **Rule:**
  - In circular conduit, the diameter comes from the tables of maximum number of cables per conduit in 770 Ed. 2017: **770.10.VII** (steel RS/RL), **770.10.VIII** (rigid insulating RP/RSP) and **770.10.IX** (corrugated CSP/CL). 771 Ed. 2006 has a single table, 771.12.IX, for steel RS/RL.
  - The **35 %** fill (insulated cables over the internal cross-section) applies **only** to surface trunking, non-circular ducts and cases not listed in the tables. For 1 to 50 mm² in circular conduit, the table governs.
  - Minimum internal diameter of **15 mm** (RL/RS 19, RSP/RP 20, commercial 3/4") on main lines and sub-mains. In 770, the conduit between the main panel and the first sub-panel (TS, *tablero seccional*), including that of the riser shafts (*columnas montantes*), is R19 / R20 at least.
  - Minimum internal diameter of **13 mm** (RL/RS 16, RSP/RP 16, commercial 5/8") on final circuits.
  - These minimums are a floor: if the table gives more for the chosen cross-section, the table governs.
  - If the conduit is not smooth inside (corrugated), choose **the next size up** from the smooth-conduit size.
  - **Crossings of walls, slabs, beams or columns with a single cable per non-metallic conduit** (straight run): internal diameter of at least **1.5 times** the outer diameter of the cable.
- **Why:** with the conduit full, the cable gets stripped while pulling, dissipates heat worse and can never be rewired.
- **How:**
  - For phases of **more than 2.5 mm² and up to 16 mm²**, the PE is counted with the same cross-section as the phases. Up to 2.5 mm², the tables already include a 2.5 mm² PE.
  - **Minimums for 2 conductors + PE, according to tables 770.10.VII to IX:**

| Cross-section (2 + PE) | Steel (VII) | Rigid insulating (VIII) | Corrugated (IX) |
|---|---|---|---|
| 2.5 mm² | RS 16 / RL 16 | RP 16 / RSP 16 | 19 (CSP 19 / CL 19): the table allows CL 16, but AEA note 3 takes corrugated to 19-20 |
| 6 mm² | RL 19 or RS 22 | RSP 20 or RP 22 | CL 22 or CSP 25 (not CSP 22) |
| 10 mm² | RL 22 or RS 25 | RP 25 / RSP 25 | CSP 32 / CL 32 |
| 16 mm² | RL 25 or RS 32 | RP 32 / RSP 32 | CSP 32 / CL 32 |

  - **AEA example:** 2 × 2.5 mm² + PE fit in RS 16 / RP 16 (5/8"). If the conduit is corrugated, go up to a size equivalent to RS 19 / RP 20 (3/4").
  - **35 % example (only to see why the catalog diameter is not used).** A conduit with a 15 mm internal diameter has a cross-section of π × 7.5² = 176.7 mm², and 35 % of it is 61.9 mm². For 2.5 mm² the AEA takes a maximum outer diameter of **4.2 mm** (13.85 mm² per cable): 61.9 / 13.85 = 4.47, that is **4 cables**. If you used the typical 3.6 mm from a catalog, you would get 6 cables, and that is wrong. For 2.5 mm² the table gives RS 19 = 4 + PE, RP 20 = 4 + PE and CL 19 = 3 + PE.
  - **Crossing example:** a sheathed cable with a 14 mm outer diameter that crosses a slab alone, in PVC conduit, needs a conduit of at least 1.5 × 14 = 21 mm internal.
  - Practical site criterion: don't go below 3/4" in any conduit, even though the minimum for final circuits is 5/8".
- **Verify:** the cable goes in and comes out by hand without forcing. The AEA considers it compliant if the tables are respected.
- **Don't:** put a single single-core cable in a metal conduit, because current is induced in the conduit and heats it; add "un circuito más" (one more circuit) to a conduit that is already full; use the 35 % with catalog diameters to justify more cables than the table gives.
- **Source:**
  - AEA 90364-7-770 Ed. 2017: 770.10.3.3.4 e) (tables for smooth conduit; next size up for non-smooth conduit; note 3 with the corrugated example), 770.10.3.8.4 (PE equal to the phase between more than 2.5 and 16 mm², 35 %, 15 and 13 mm) and tables 770.10.VII, VIII and IX (maximum outer diameters: 2.5 mm² → 4.20 mm; 6 mm² → 6.30 mm; 10 mm² → 7.60 mm). Also 770.7.1 p): R19 / R20 between the main panel and the first sub-panel, including risers.
  - AEA 90364-7-771 Ed. 2006, 771.12.3.13.4 (table 771.12.IX, 35 %, 1.5 × D at crossings, 15 and 13 mm) and 771.8.5 t) (R19 between the main panel and the first sub-panel, also in risers).
  - The text of 770.10.3.3.4 e) 2 says "inmediatamente superior al establecido por las tablas 770.10.IX" (immediately above the one established by tables 770.10.IX). This guide reads it as the example in note 3: the next size up from the smallest smooth-conduit size. That reading matches table IX at 6, 10 and 16 mm², and at 2.5 mm² gives 19 instead of the table's CL 16. If your authority reads it as one size more than table IX, go up one size.

### ELEC-CON-13: Bends, junction boxes and distances
- **Rule:**
  - Maximum **3 bends** between two consecutive boxes or enclosures. A bend is a change of direction with an interior angle between 90° and 135°; no bend closes to less than 90°.
  - Between two consecutive bends, at least **10 times the outer diameter** of the conduit.
  - On straight runs without branches, a junction box at most every:
    - **770 Ed. 2017:** **15 m**, horizontal or vertical;
    - **771 Ed. 2006:** **12 m** horizontal and **15 m** vertical.
  - At expansion joints, a box on each side, joined with sheathed flexible steel conduit.
  - Orthogonal routing: vertical and horizontal lines parallel to the edges of the room.
- **Why:** each bend multiplies the pulling force. With more than three bends the cable gets stripped or simply does not go through, and whoever comes to rewire has to break the wall.
- **How:**
  - Minimum bending radii (table 770.10.V), up to 32 mm outer diameter: corrugated and rigid insulating, about **3 times** the outer diameter (for example 60 mm for a 20 mm conduit); smooth pliable and rigid metal, about **6 times** (120 mm for 20 mm). At larger diameters the radii grow more than that: 40 mm corrugated requires 160 mm and 50 mm smooth pliable requires 480 mm. See the table.
  - Factory steel bends have their own radii (table 770.10.VI).
  - Orthogonal routing is mandatory on the surface and embedded in masonry, and recommended in dry construction. That way, whoever drills the wall later knows where not to drill.
- **Verify:** count the bends between boxes on the drawing and on site before covering. In a long hallway of an apartment (771), a box every 12 m at most.
- **Don't:** diagonal runs across the wall or slab; "S" bends and reverse bends to dodge beams without an intermediate box.
- **Source:** AEA 90364-7-770 Ed. 2017: 770.10.3.1, 770.10.3.6.2, 770.10.3.6.4 and tables 770.10.V and 770.10.VI. AEA 90364-7-771 Ed. 2006, 771.12.3.8.3 (12 m horizontal, 15 m vertical; expansion joints).

### ELEC-CON-14: Boxes
- **Rule:**
  - Every conduit run ends in an outlet point, box or enclosure; fixed-connection circuits can run up to the equipment's box.
  - Switches, socket outlets and protective devices always go inside boxes.
  - Junction and branch boxes remain **accessible**.
  - The box size comes from the volume taken up by cables and devices.
  - On the surface, boxes with knockouts that can be removed without a tool are not used. Unused holes are closed with plugs that require a tool.
  - Conduit-to-box joints are made with a connector or with a nut and bushing, metal on metal conduit and synthetic on synthetic conduit. In seismic zones (above AP1), in slabs and ceilings, use nut, locknut and bushing.
  - The conduit ends in a fitting with rounded edges.
  - Boxes and panels are no less than 50 cm from the outlets and valves of the gas installation.
- **Why:** an overloaded box presses the splices against the metal cover; an inaccessible box (covered by tiles or by furniture) prevents inspecting or changing the wiring.
- **How:** add up the volume of each cable that passes through or branches and that of the devices, and compare with the usable volume of the box (tables 770.10.X to XII).
  - **Indicative example.** The 5 × 10 rectangular box has 120 cm³ usable. An intermediate socket outlet on a 2.5 mm² circuit receives phase, neutral and PE coming in and another three going out: 6 cables × 8.5 cm³ = 51 cm³. With a 10 A 2P+E socket outlet (18 to 38 cm³) you take up 69 to 89 cm³: it fits.
  - If another general-purpose circuit also passes through (3 more cables, +25.5 cm³), you reach 94.5 to 114.5 cm³: you are at the limit. Choose a 10 × 10 square box (200 cm³ usable).
- **Verify:** with the circuit switched off and verified dead, open the boxes: the cables are not taut, no splice touches the cover and there is the spare cable length from ELEC-CON-20 (0.1 m in 770, 150 mm in 771).
- **Don't:** leave splices in boxes covered by wall finishes; use a switch box as the branch box of another circuit.
- **Source:** AEA 90364-7-770 Ed. 2017: 770.10.3.1, 770.10.3.4, 770.10.3.6.1, 770.10.3.8.1, 770.10.3.8.2 f), tables 770.10.X to 770.10.XII and 770.17 (50 cm from gas installations). AEA 90364-7-771 Ed. 2006, 771.12.3.13.1 (150 mm spare length).

### ELEC-CON-15: Embedded conduit: mechanical protection and work sequence
- **Rule:** embedded light steel conduit or insulating conduit with a classification lower than 4.3.2.1 (IRAM 62386-1) is protected in one of these three ways:
  - a) it lies **50 mm** or more from the finished surface;
  - b) it has a steel barrier of 1.4 mm or more, 5 mm wider than the conduit on each side;
  - c) it has a layer of 1:3 mortar (cement:sand, without lime or plaster) 10 mm or more thick, 10 mm wider than the conduit.

  In slabs the protection is considered met. The 100 mm strips next to door and window frames and around boxes are exempt.
- **Why:** the nail for a picture, the wall plug for a cabinet or the angle grinder of the next trade go through a light conduit left 1 cm from the surface.
- **How:** in all cases cover the conduit with mortar, which protects it from corrosion (metal) or from impacts (insulating). **Pull the cables only once** the installation of conduit and boxes and the plastering and finishes that could damage them are complete.
- **Verify:** before plastering, check the depth of the chases and photograph the routes for the as-built drawing.
- **Don't:** pull cables before plastering "para adelantar" (to get ahead); leave the conduit flush with the brick and plaster over it.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.10.3.3 and 770.10.3.8.1. AEA 90364-7-771 Ed. 2006, 771.12.3.13.1 (pull cables after finishing wiring systems and finishes).

### ELEC-CON-16: Surface conduit and conduit above a suspended ceiling
- **Rule:**
  - **On the surface:**
    - every conduit of 2 m or more is fixed at no fewer than 3 points per 3 m run; those under 2 m, at no fewer than 2 points;
    - bends are fixed at the entry and exit, 0.2 m or less from the vertex;
    - each conduit is fixed 0.5 m or less from each box, and each box at no fewer than 2 points;
    - in damp locations, conduit, boxes and enclosures stand off at least 0.01 m from the wall;
    - every wiring system is more than 0.2 m from chimneys, exhausts or hot ducts, or is thermally insulated.
  - **Above a suspended ceiling:** wiring systems are fixed to or suspended **from the slab**, never resting on the ceiling. If they are suspended, they form a rigid structure and cannot be corrugated.
- **Why:** a badly fixed conduit moves every time something is plugged in, loosens connections and ends up hanging. The ceiling is not designed for that weight.
- **How:** use fittings suitable for surface mounting: galvanized steel, aluminum, brass, stainless or insulating material. Surface trunking must meet tables 770.10.III and IV: minimum IP according to the location and HIGH ("ALTA") UV protection if exposed to sun (ELEC-CON-29).
- **Verify:** push and pull a plug (*ficha*) inserted in a suspended box: the assembly does not move.
- **Don't:** rest the conduit on the ceiling framing; use indoor surface trunking outdoors.
- **Source:** AEA 90364-7-770 Ed. 2017: 770.10.3.4 h) to n), 770.10.3.5 and tables 770.10.III and 770.10.IV.
### ELEC-CON-17: Cable trays (*bandejas portacables*)
- **Rule:**
  - In a cable tray (*bandeja portacables*) use **sheathed cables** (IRAM 2178-1 / 62266, or IRAM 2268).
  - **Exception:** the PE may be a single-core IRAM NM 247-3 or 62267 conductor, and in risers (*columnas montantes*) with a tray it may also be bare.
  - Metal trays are connected to the PE and their continuity is verified.
  - Under the 771, main lines and sub-mains may run in a tray without the limit of three sub-mains per conduit.
  - The design (tray type, fill, spacing, grouping factors) follows AEA 90364-5-52, clause 521.12.
- **Why:** in a tray the cable is exposed: without a sheath it has no mechanical protection (ELEC-CON-2).
- **How:** in risers and machine rooms of buildings, a tray with sheathed cables is usually more practical than many parallel conduits (ELEC-CON-23). Use the "in tray" current-carrying capacity (table 771.16.III and factors from 771.16.IV, items 4 and 5), not the conduit one. Drops and wall crossings in conduit or wall sleeves. In a riser, the amount of combustible material per meter of tray and the sealing between floors have their own limits (ELEC-CON-25).
- **Verify:** no unsheathed single-core cable in the tray, except the PE; PE continuity along the tray.
- **Don't:** use the tray as the PE; lay data cables mixed with power cables without a divider (ELEC-CON-18).
- **Source:**
  - AEA 90364-7-771 Ed. 2006: table 771.12.I and its note 1 (NM 247-3 and 62267 in a tray or in a buried duct "sólo… como conductor de protección" (only... as protective conductor)); 771.12.1 h); 771.12.3.12.3 d) (risers with a tray: PE may also be bare); notes to 771.12.3.13.2 b) and c) (trays with no limit on quantity).
  - AEA 90364-7-770 Ed. 2017, 770.10.2 (single-core cables only in conduit or surface trunking), 770.10.3.7 (refers to AEA 90364-5-52, 521.12) and 770.10.3.2 (earthing of metal wiring systems).
  - **Not verified in a primary source:** the details of 521.12, which was not consulted.

### ELEC-CON-18: Separation of 220/380 V and low-current systems
- **Rule:** these go in **separate wiring systems**:
  1. the 380/220 V system;
  2. MBTS / MBTF (up to 24 V);
  3. weak signals: TV, door intercom, alarms, video;
  4. data: internet, network.

  If they cannot be separated, apply one of these measures:
  - put the low-voltage cables inside another conduit or insulating cover;
  - separate them with an earthed metal screen;
  - use a multicore cable with all conductors insulated for the higher voltage.
- **Why:** an insulation fault puts 220 V on an intercom or network cable that someone touches without protection; also, power wiring induces noise in data and video.
- **How:** plan separate conduits and boxes for data and TV from the design stage. Shared boxes only with a divider.
- **Verify:** open the boxes: there is no UTP or coax next to the 220 V cables without separation.
- **Don't:** run the network cable through the socket outlet conduit "because there was room left".
- **Source:** AEA 90364-7-770 Ed. 2017, 770.10.3.8.2 h), notes 1 and 2. AEA 90364-7-771 Ed. 2006, 771.12.3.13.2 h), which adds analog or digital control and telephony.

### ELEC-CON-19: Underground runs
- **Rule:**
  - Only sheathed cables (IRAM 2178-1 / 62266) are buried, directly or in a duct. In a buried duct, a single-core NM 247-3 or 62267 cable is only allowed as the PE.
  - **Directly buried:**
    - minimum depth **0.7 m**, on a firm, smooth, stone-free bed;
    - mechanical protection with a half-round cover or cement slab, or with whole bricks laid crosswise (at least 0.25 × 0.09 × 0.05 m) over sand or sifted soil;
    - red, or red and white, **warning tape** "PELIGRO ELÉCTRICO" (electrical hazard), at **0.2 m** below the surface along the whole length of the trench.
  - **In a duct:**
    - minimum cover of 0.7 m over the conduit;
    - slope of 1 % or more toward the pits;
    - minimum diameter, **for one cable per conduit**: 50 mm for cables up to 25 mm in diameter, 100 mm for cables from 25 to 66 mm, and 1.5 times the cable diameter if larger. With more cables per conduit, check the fill (ELEC-CON-12);
    - IRAM 62386-24 conduits with "normal" impact resistance, or "light" if encased in concrete;
    - IRAM 13350 PVC conduit only with the same mechanical protection as a directly buried cable.
  - **Under buildings:** always in a duct, extending **0.30 m** beyond the perimeter.
- **Why:** the shovel, the gardener's post-hole digger or the neighbor's machine find the cable before anyone else. The tape warns before the blow and the bricks stop it.
- **How:**
  - **Before digging:** ask for drawings of existing services (gas, water, sewer, telephone, the installation itself) and check with the local utility companies. Locate cables with a cable or metal detector and dig by hand, with a shovel and no pick, near any likely route. **Danger:** breaking a live buried cable or a gas pipe can kill. If a cable or pipe appears that was not on the drawing, stop and ask.
  - **Crossings and parallel runs with other services:** cross at right angles, don't lay the cable over or under a gas or water pipe along its route, and leave separation with fill material between the two.
  - Respect the manufacturer's bending radii at changes of direction.
  - For current-carrying capacity, use the buried column of table 770.12.III (25 °C soil, 1 K·m/W).
  - Leave inspection pits at changes of direction of the duct banks.
- **Verify:** before backfilling, photograph the trench with a tape measure, the protection and the warning tape, and mark the route on the as-built drawing.
- **Don't:** bury single-core cables inside a garden hose; backfill without warning tape; bury at 30 cm "because it's just the yard"; dig with a machine without having located the services.
- **Source:** AEA 90364-7-770 Ed. 2017: 770.10.4.1 to 770.10.4.2.3 and table 770.10.XIV ("un cable por caño", one cable per conduit). AEA 90364-7-771 Ed. 2006, table 771.12.I, note 1. **Not verified in a primary source:** the minimum crossing and parallel distances with gas, water, sewer and telecommunications. They are in AEA 95101 (outdoor underground lines) and in the utility companies' regulations, which could not be consulted. Ask the designer or the utility company for them.

## Laying and connections

### ELEC-CON-20: How to pull cables
- **Rule:**
  - Don't pull the cable with more than **50 N/mm²** of conductor cross-section during installation, and don't leave it under more than **15 N/mm²** in permanent service.
  - Cable slack in each box: at least **0.1 m** under the 770 and **150 mm** under the 771. In practice, always leave 0.15 m. Cables that pass through without a splice form a loop.
  - In vertical conduit runs, the cable is supported in accessible boxes every **15 m** at most, with supports that don't damage the insulation.
  - **Conductors in parallel:** circuits (main, sub-main or final) are not made with conductors in parallel. Only if the current exceeds the current-carrying capacity of the largest cable available are parallel branches allowed, with the protection of chapter 43 and the installation of chapter 52. In a tray they go in the arrangements set by the AEA.
- **Why:** an overstretched cable loses cross-section and its insulation is damaged without it being visible. In a tall riser, the weight of the cable hangs from the panel terminals. Two cables badly run in parallel share the current poorly and one overheats without the protection noticing.
- **How:**
  - Maximum pulling force = 50 N/mm² × cross-section × number of conductors. Example: 3 conductors of 2.5 mm² → 50 × 2.5 × 3 = 375 N (about 38 kgf).
  - Use a fish tape or cable guide and cable-pulling lubricant, not oil or detergent.
  - **Danger:** never rewire a conduit with energized circuits next to it. Switch off, lock out and verify absence of voltage first (see [site-safety.md](site-safety.md)).
  - In a house or an apartment, "doubling" a cable to gain cross-section is not a solution: use the next cross-section up.
- **Verify:** after pulling, measure the insulation between conductors and to earth (see [testing-and-commissioning.md](testing-and-commissioning.md)). A low value usually indicates a cable stripped during the pull. **Before measuring:**
  - the installation must be switched off and verified dead;
  - disconnect loads, SPDs (*DPS*), LED drivers, timers and electronic equipment;
  - warn the other trades: nobody touches the cables while measuring, because the megohmmeter applies 500 V DC;
  - when finished, discharge the conductors.
- **Don't:** pull with the pickup truck or with a hoist without measuring the force; use the old cable as a guide for the new one in conduits with tight bends; put two cables in parallel in a dwelling circuit.
- **Source:** AEA 90364-7-770 Ed. 2017, 770.10.3.8.1. AEA 90364-7-771 Ed. 2006, 771.12.3.13.1 (150 mm; conductors in parallel). Insulation test voltage: IEC 60364-6, 6.4.3.3 (500 V DC for circuits up to 500 V); the details are in [testing-and-commissioning.md](testing-and-commissioning.md).

### ELEC-CON-21: Splices and branches: only in boxes, never inside the conduit
- **Rule:**
  - **Splices and branches are not allowed inside conduits.** They are made only in accessible boxes.
  - **Cross-sections smaller than 4 mm²:** up to 4 conductors, interleaving and twisting the strands.
  - **4 mm²:** up to 3 conductors, in the same way.
  - **More than 4 cables together:** IRAM 2441 terminal block, or another IEC-standard terminal block.
  - **Cross-sections larger than 4 mm²:** terminal blocks, crimp (compression) sleeves or low-melting-point solder with non-acid flux, or another joint with conductivity equal to or greater than that of the cable.
  - Every splice is covered with insulation equivalent to that of the cable and is not subjected to mechanical stress.
- **Why:** the splice is the weakest point of the circuit. Inside the conduit it can't be seen or checked and, when it heats up, it burns the conduit and the neighboring cables.
- **How:**
  - Standardized spring or lever connectors (IEC 60998 / EN 60998): respect the cross-section and number of conductors each one accepts.
  - Sleeves: the die and the tool must be the ones the manufacturer specifies.
  - A low-melting-point solder limits the allowable short-circuit temperature of the whole line to **160 °C**. In PVC cables nothing changes, because their limit is already 160 °C. It matters in cables with XLPE insulation (IRAM 2178-1), whose limit is about 250 °C: with solder, check the short circuit as if they were PVC (see ELEC-CON-26 and [protection.md](protection.md)).
- **Verify:** with the circuit switched off and verified dead, pull on each conductor of the splice. At commissioning, under load, look for splices that heat up with an infrared thermometer or a thermal camera, from a distance and with the cover on. Don't touch covers to "feel" heat: a metal cover can become live if a splice touches it and the PE fails. If you find a hot spot, switch off, verify absence of voltage and only then open and redo the splice.
- **Don't:** splice with tape only; leave splices "hanging" inside the conduit to avoid fitting a box; splice two different cross-sections by twisting when one is larger than 4 mm².
- **Source:** AEA 90364-7-770 Ed. 2017, 770.10.3.8.1 and 770.10.3.8.3. AEA 90364-7-771 Ed. 2006, 771.12.3.13.3 (low-melting-point solder "puede limitar la temperatura máxima de cortocircuito de toda la línea a 160 °C" (may limit the maximum short-circuit temperature of the whole line to 160 °C)). Limits of 160 °C (PVC) and 250 °C (XLPE): IEC 60364-4-43, 434.5.2. IEC 60998 is a general product reference (medium confidence).

### ELEC-CON-22: Aluminum to copper: only with bimetallic connectors
- **Rule:** never use an ordinary terminal or clamp (*morseto*) to join aluminum to copper. You need a **bimetallic** (Al-Cu) lug or connector, or an insulation-piercing connector (IPC) rated for both metals, with inhibitor grease if the manufacturer specifies it.
- **Why:**
  - With moisture, aluminum and copper form a galvanic couple: the aluminum corrodes and the contact resistance rises.
  - Also, aluminum creeps under pressure (it "loosens" with thermal cycles) and forms an insulating oxide layer.
  - The result is a hot spot at the connection, typical in service connections and meter pillars (*pilares*).
- **How:**
  - In buildings, aluminum appears almost only in the service connection (IRAM 2263 aerial bundled cable, *preensamblado*) and in large feeders.
  - On the utility (distribution company) side, the connection is made by the utility.
  - On the user side, use Al-Cu compression lugs with the correct die and retighten to the manufacturer's torque, always de-energized.
  - The AEA 770 current-carrying capacity tables for dwellings are given for copper only.
- **Verify:** at the meter pillar, look for white oxide or discoloration at the connection. Under load, thermography detects connections that heat up, always without opening live parts.
- **Don't:** splice aluminum and copper by twisting; use copper lugs on an aluminum cable.
- **Source:**
  - Copper-only tables: AEA 90364-7-770 Ed. 2017, tables 770.12.I and III.
  - Aerial bundled aluminum cable appears in the normative references (IRAM 2263).
  - **Not verified in a primary source:** a specific AEA clause on Al-Cu connections. The criterion of avoiding electrolytic corrosion appears in IEC 60364-5-52, clause 526 (connections), and in the instructions of bimetallic lug manufacturers.

## Buildings: the riser (single-phase 4-floor case)

### ELEC-CON-23: Riser (*montante*) from the meter panel to each apartment
- **Rule:** in a building with meters grouped on the ground floor:
  - the **main panel** of each apartment (*depto*) goes inside the property, **no more than 2 m** from its meter, that is, in the meter room or meter cabinet. From there, each apartment has its own **sub-main (feeder)**, in its own conduit, up to the apartment's general sub-panel (TS, *tablero seccional*);
  - if, by agreement with the utility or the authority, the main panel is inside the apartment, what goes up is the **main line**: minimum 4 mm², with double or reinforced insulation along its whole route, and the voltage drop is measured only from the apartment panel (see [buildings.md](buildings.md));
  - the exception of up to 3 sheathed sub-mains in one conduit requires them to be **from the same meter**. It never applies between apartments, because each one has its own meter. It does apply to several sub-mains of the same apartment or of common services;
  - the cross-section is sized by current-carrying capacity (with grouping), by voltage drop and by short circuit, with the PE in the same conduit and without sharing the PE between meters;
  - common services (stairs, landing, pump, door intercom, elevator) are a separate installation, with their own meter and panel, and are governed by AEA 90364-7-772. The sub-mains in the riser must also comply with the 772.
- **Why:** if lines from different meters are mixed, when one apartment's MCB (*térmica*) is switched off there can still be voltage from another in the same junction box. And an undersized riser shows up as low voltage on the upper floors.
- **How:** example with ground floor + 4 floors, 2 apartments per floor, single-phase 220 V and apartments under the 771.
  1. **Route.** One vertical riser in an accessible shaft, with one junction box per floor. The floor-to-floor height is about 3 m, so the box every 15 m vertically is easily met.
  2. **Cross-section by voltage drop.** The calculation in ELEC-CON-9 gives 10 mm² for 25 A at 20 m (4th floor), with a 0.86 % drop. The cross-section depends on the Ib adopted: with the roughly 7 kVA (31.8 A) per apartment of the case in [buildings.md](buildings.md) (ELEC-EDI-8), 10 mm² gives 1.14 % and **16 mm²** is needed; with air conditioners in every apartment, the Ib goes up and the cross-section may go up too. The agent runs it with `gateway electricidad size --current IB --length 20 --circuit submain --norm 771 --grouped 8` (and `--layout layer` if the conduits run in a single layer). With 6 mm² it would give 1.45 %, which exceeds the mandatory 1 % of the 771. The lower floors could use 6 mm² if the calculation gives ≤ 1 % (1st floor, about 8 m: 6.5 × 25 × 0.008 = 1.30 V → 0.59 %), but a single cross-section simplifies the job and the purchase.
  3. **Protection at the origin and grouping.** Each sub-main leaves protected against overload and short circuit from its apartment's main panel, in the meter room (see [protection.md](protection.md) and [panels.md](panels.md)). Choose In and verify IB ≤ In ≤ Iz, with Iz corrected for the 8 conduits of the riser, which all run together on the ground floor:
     - IB = 25 A; In = 32 A;
     - conduits in **a single layer** on the shaft wall (Fa 0.71 for 8): Iz = 50 A × 0.71 = 35.5 A ≥ 32 A. **Complies**;
     - conduits **bunched** (Fa 0.52): Iz = 50 × 0.52 = 26 A < 32 A. **Does not comply**. Options: In = 25 A (26 ≥ 25, just), arrange the conduits in a single layer or space them apart, or go up to 16 mm² (66 × 0.52 = 34.3 A ≥ 32 A).
  4. **Wiring system.** One of two:
     - **a) Conduits, one per apartment**, with 2 conductors + PE, single-core IRAM NM 247-3 (or 62267). The diameter comes from tables 770.10.VII to IX for the chosen cross-section (ELEC-CON-12). For 2 × 10 mm² + PE: steel RL 22 or RS 25 (1"), rigid insulating RP 25 / RSP 25, corrugated 32. A 3/4" conduit (RS 19 / RP 20) **is not enough**: the 15 mm internal diameter is only the minimum for sub-mains;
     - **b) Tray in the shaft** with IRAM 2178-1 sheathed cables (or 62266 if the project calls for LS0H). Under the 771, sub-mains may run in a tray without the limit of three. Use the tray current-carrying capacity and its grouping factor (771.16.III and IV, items 4 and 5), and respect the limit of combustible material per meter (ELEC-CON-25).
  5. **Short circuit.** Check the cross-section against the Icc at the meter panel (ELEC-CON-26).
  6. **Support.** In vertical runs longer than 15 m (not this case), supports in accessible boxes (ELEC-CON-20).
  7. **Identification.** Each line is labeled at both ends and in each junction box with the apartment number.
  8. **Floor penetrations.** They are sealed with firestop material (ELEC-CON-25).
- **Verify:**
  - with everything de-energized and locked out, the continuity of each line end to end and its match with the apartment number;
  - the insulation of each line, with the precautions of ELEC-CON-20 (installation switched off and dead, loads and SPDs disconnected, nobody touches the cables during the test, discharge at the end);
  - under load, the voltage at the 4th-floor panel compared with that on the ground floor;
  - the technical report shows for each line In, Iz corrected for grouping, ΔU% and I²t.

  See [testing-and-commissioning.md](testing-and-commissioning.md).
- **Don't:** a single large conduit with all the single-core lines of all the apartments; put 2 × 10 mm² + PE in a 3/4" conduit; take the common services from an apartment's line; splice a sub-main halfway up the riser; size with the current for a single conduit when 8 conduits run up side by side.
- **Source:**
  - AEA 90364-7-770 Ed. 2017: 770.10.3.8.2 b) and c), 770.10.3.8.4, tables 770.10.VII to IX, 770.10.3.6.2, 770.15.6, 770.16.3.1 (main panel at ≤ 2 m, Class II, exception by agreement, main line with double insulation) and 770.7.1 p).
  - AEA 90364-7-771 Ed. 2006: 771.13 b) (mandatory 1 %), 771.20.3.1 (2 m), 771.12.3.12.3 h) (the PE accompanies the circuits of the same meter and is not shared between meters), 771.12.3.13.2 c) with its note (trays), 771.16.IV (grouping) and 771.18.5 t).
  - AEA 90364-7-772 Ed. 2019, 772.1.1: the dwellings in the building are governed by the 770 or the 771, and the sub-mains in risers must also comply with the 772.
  - Applying table 771.16.IV to separate conduits that touch is a criterion of this guide, because item 1 includes "embutidos o encerrados" (embedded or enclosed). Confirm it with the designer.
  - **Not verified in a primary source:** the additional requirements of the 772 for sub-mains in risers (only its 772.1.1 could be read) and each utility's requirements for meter panels. See [buildings.md](buildings.md), [panels.md](panels.md) and the utility's supply regulations.
## 770 or 771: what changes

### ELEC-CON-24: Decide whether the 770 or the 771 applies before sizing, and use its values
- **Rule:** before choosing cross-sections, conduits and boxes, write down in the technical report which AEA section applies to each unit. In an apartment (*depto*), the default is the 771 (ELEC-CIR-1 in [grades-and-circuits.md](grades-and-circuits.md)). Where they differ, apply the value of the section that applies; if that is not defined, the stricter one.

| Topic | 770 Ed. 2017 | 771 Ed. 2006 |
|---|---|---|
| Supply and return of light switches | 1 mm² (table 770.11.I) | 1.5 mm² (table 771.13.I) |
| Voltage drop in sub-mains | 1 % recommended (770.15.6) | 1 % mandatory; final circuit ≤ 2 % (≤ 4 % with motors) from the sub-panel (TS, *tablero seccional*) (771.13 b) |
| Junction box on a straight run | every 15 m, horizontal or vertical (770.10.3.6.2) | every 12 m horizontally and 15 m vertically (771.12.3.8.3) |
| Cable slack in each box | 0.1 m (770.10.3.8.1) | 150 mm (771.12.3.13.1) |
| Main lines and sub-mains in a cable tray | only refers to AEA 90364-5-52 (770.10.3.7) | allowed, without the limit of 3 sub-mains (notes to 771.12.3.13.2 b and c) |
| Tables of cables per conduit | steel (VII), rigid insulating (VIII), corrugated (IX) | steel RS/RL only (771.12.IX) |
| LS0H | outside its scope (with BD2 or higher the 771 applies) | column 1 of table 771.12.I (ELEC-CON-4) |
| Risers (*columnas montantes*) | only minimum diameter R19 / R20 (770.7.1 p) | open, closed or embedded classification, and requirements (771.12.3.12) |

  **Same in both:**
  - voltage drop limits of 3 % and 5 % / 15 %;
  - up to 3 general-purpose circuits per conduit (36 A, 15 outlet points);
  - 35 % fill outside the tables; 15 mm and 13 mm minimum diameter;
  - 50 / 15 N/mm² pulling tension; support every 15 m on vertical runs;
  - current-carrying capacities (770.12.I = 771.16.I) and grouping of 0.80 / 0.70;
  - the other minimum cross-sections.
- **Why:** the two sections give different numbers for the same thing. An installation done "to the 770" in an apartment that the authority reviews under the 771 can get observations for 1 mm² returns, a sub-main at 1.3 % or boxes at 15 m in a hallway.
- **How:** the 770 requires all of the following at once: incoming device up to 63 A, prospective short-circuit current up to 10 kA at the origin, BA2 users and BD1 evacuation. If any of the three conditions fails, or if it is an office or shop, the 771 applies. In a building, the Icc in the meter room is given by the utility (distribution company) and can exceed 10 kA near the transformer.
- **Verify:** the technical report names the section and edition per unit, and the values in the table match that section.
- **Don't:** mix values from the two sections in the same unit; assume that an apartment "is a dwelling, so 770".
- **Source:** AEA 90364-7-770 Ed. 2017, 770.1 (scope: single-family houses with 63 A, 10 kA, BA2 and BD1) and general considerations (with more than 63 A, BA3 to BA5, BD2 to BD4, offices or shops "se debe continuar aplicando la Sección 771" (Section 771 must continue to be applied)). AEA 90364-7-772 Ed. 2019, 772.1.1 ("770 ó 771, según corresponda", 770 or 771, as applicable). The clauses for each row are cited in the table, and all were read in the primary text of each section.

### ELEC-CON-25: Riser (*montante*) and floor penetrations: firestop sealing and combustible load
- **Rule:**
  - Penetration holes between floors (conduits, cable trays, ducts) are sealed with material whose fire resistance is **at least equivalent** to that of the material removed to make the penetration, or to what the project specifies. It is mandatory under the 771, not a recommendation.
  - An **open riser** (insulating conduits or exposed cables, or an enclosure below F60 or below IP54) spreads fire and smoke. A **closed** riser has an enclosure or boxes rated F60 (or the fire resistance of the room) and IP54 as a minimum. An **embedded** riser keeps those conditions at its access boxes.
  - In metal cable trays in risers, the synthetic material per meter of tray (cables plus insulating conduits) does not exceed:
    - **1.5 dm³/m** with category C cables (IRAM NM IEC 60332-3-24);
    - **3.5 dm³/m** with category B (60332-3-23);
    - **7 dm³/m** with category A (60332-3-22).

    If it is exceeded, split the cables into trays separated by fire-resistant partitions or by distance, use another wiring system or close the riser.
  - Cables exposed to the air inside the building for more than 2.5 m (for example in an open tray) pass the IRAM NM IEC 60332-3-24 test, category C.
  - The PE accompanies the circuits of **the same meter**: it is not shared between meters.
  - The riser preferably goes in its own shaft, effectively separated from the other services.
- **Why:** an unsealed shaft works like a chimney: it carries the smoke of a ground-floor fire to every floor in minutes. The amount of PVC per meter of tray is fuel that feeds that chimney.
- **How:**
  1. Agree with the designer whether the riser is open, closed or embedded, and choose cables and wiring systems from table 771.12.I (ELEC-CON-4).
  2. Calculate the volume of synthetic material per meter: π × (D/2)² for each cable, plus the insulating conduit. Example: 8 sheathed cables of 14 mm outer diameter are 8 × π × 0.7² cm² = 12.3 cm² of cross-section, that is, 1.23 dm³ per meter. It fits within the 1.5 dm³/m limit (category C) with little margin. This calculation counts the whole cable as synthetic, which is the conservative approach.
  3. At each slab, after pulling the cables, seal the penetration. On site, people use intumescent sealants or putties, firestop mortars, intumescent pillows or bags in large tray penetrations, and intumescent collars on plastic conduits. Use products with a fire resistance test declared by the manufacturer and follow their instructions (thickness, depth, backing).
  4. Record on the as-built drawing what was sealed and with which product, and reseal every time someone runs a new cable.
- **Verify:** from each floor, the slab penetration shows no light and lets no air through; the riser covers close; the tray holds no more cables than the ones in the calculation.
- **Don't:** seal with ordinary polyurethane foam, expanded polystyrene (*telgopor*) or rags; leave the shaft open "to run cables later"; put gas or water pipes in the electrical shaft without separation.
- **Source:** AEA 90364-7-771 Ed. 2006: 771.12.3.12.2 (open, closed and embedded risers; F60 and IP54), 771.12.3.12.3 a) to h), and table 771.12.I, notes 1 (combustible material per meter of tray) and 6 (sealing). In condominium buildings (*propiedad horizontal*), note 1 d) expressly refers to closing the penetration holes. **Not verified in a primary source:** what each municipal building code or each fire department requires for sealing, and the firestop materials named in step 3, which come from site practice and not from a consulted standard. Confirm with the municipality and with the product data sheet.

### ELEC-CON-26: Check that the cross-section withstands the short circuit (k²S² ≥ I²t)
- **Rule:** in addition to current and voltage drop, each line must withstand the energy of the maximum short circuit until the protection trips: **k² × S² ≥ I²t**, with k = 115 for copper with PVC insulation (from 70 °C to 160 °C).
- **Why:** in a short circuit the current is thousands of amperes. If the protection takes longer than the cable can withstand, the insulation melts before it trips, even if the cable is correctly chosen for the load.
- **How:**
  - Ask the utility for the prospective short-circuit current (Icc) at the panel, or calculate it (see [protection.md](protection.md)).
  - If the breaker is current-limiting (PIA class 3), I²t is the let-through energy figure the manufacturer gives at that Icc.
  - If it is not current-limiting, take t = 0.1 s and check S ≥ Icc × √t / k.
  - **Example (riser from ELEC-CON-23).** Assumed Icc in the meter room: 3 kA (figure to request from the utility). 10 mm² line: k²S² = 115² × 10² = 13 225 × 100 = 1 322 500 A²s. With t = 0.1 s: I²t = 3000² × 0.1 = 900 000 A²s ≤ 1 322 500 A²s. **Complies**. Minimum cross-section: S = 3000 × √0.1 / 115 = 3000 × 0.316 / 115 = 8.25 mm² ≤ 10 mm².
  - **With 6 mm²** and the same non-limiting protection: k²S² = 13 225 × 36 = 476 100 A²s < 900 000 A²s. **Does not comply**: you need a current-limiting PIA whose I²t at 3 kA is ≤ 476 100 A²s, or a larger cross-section.
  - **4 mm² main line** with the same criterion of t = 0.1 s: minimum S 8.25 mm² > 4 mm². It depends on the upstream protection, which the utility sets. See ELEC-PRO-5 and [buildings.md](buildings.md).
- **Verify:** the technical report shows, for each line, Icc, k²S² and the device's I²t (manufacturer's figure or AEA guidance table).
- **Don't:** accept a cross-section "because the MCB (*térmica*) is 6 kA": the breaking capacity does not say how much energy it lets through; forget that a low-melting-point solder also limits XLPE cables to 160 °C (ELEC-CON-21).
- **Source:** AEA 90364-7-770 Ed. 2017 and 771 Ed. 2006: verification of thermal stress under short circuit (771.13, final paragraph; k per table 771.19.II / 770.15.II, cited in ELEC-PRO-5 of [protection.md](protection.md)). IEC 60364-4-43, 434.5.2. The Icc of 3 kA is an assumption of the example.

## More site cases

### ELEC-CON-27: Line from the meter pillar (*pilar*) to the house (buried or overhead)
- **Rule:**
  - The **service connection** (*acometida*, from the network to the meter) and the meter pillar are defined by the utility (AEA 95150 and its supply regulations).
  - The **main panel** goes no more than 2 m from the meter, normally in the same pillar or right next to it. Its enclosure is Class II, standardized and certified, and IP54 as a minimum outdoors.
  - The **main line** (from the meter to the main panel) is at least 4 mm² and has double or reinforced insulation, with its wiring system: sheathed cable or single-core cables in insulating conduit.
  - From the main panel in the pillar to the house it is a **sub-main (feeder)**, and it is sized by current, voltage drop and short circuit like any other (ELEC-CON-8, 9 and 26).
  - **Buried:** IRAM 2178-1 / 62266 sheathed cable, direct or in a duct, with the rules of ELEC-CON-19. Single-core NM 247-3 cables in buried conduit, only the PE.
  - **Overhead** (exclusively outdoors): IRAM 2178 / 62266 / 2268 sheathed cable with a support wire or messenger, or IRAM 2263 aerial bundled cable (*preensamblado*).
  - **Entry into the house:** the cable enters the box or panel through a cable gland. If the conduit forms a "U" or can collect water, use sheathed cable (ELEC-CON-2), and seal the entry against water.
- **Why:** it is the longest and most exposed run of a house: sun, water, the gardener's shovel. And since it is usually long, the voltage drop forces a larger cross-section than people expect.
- **How:**
  - **Example:** house 30 m from the pillar, IB = 25 A, buried sub-main.
    - 6 mm²: 6.5 × 25 × 0.030 = 4.88 V → 2.2 %;
    - 10 mm²: 3.8 × 25 × 0.030 = 2.85 V → 1.30 %;
    - 16 mm²: 2.4 × 25 × 0.030 = 1.80 V → **0.82 %** ≤ 1 %. To stay at 1 % (recommended in the 770, mandatory in the 771) you need 16 mm².

    The voltage drop table is for single-core cables in conduit, but at these cross-sections resistance dominates and it serves as guidance for sheathed cable. The buried current-carrying capacity comes from table 770.12.III.
  - The PE (or the earthing conductor, if the earth rod (*jabalina*) is at the pillar) runs with the sub-main, with the cross-section from ELEC-CON-6.
- **Verify:** route and depth photographed before backfilling (ELEC-CON-19); cable glands and seals fitted at both ends; voltage drop measured under load at the house panel.
- **Don't:** run flexible cord (*tipo taller*) or loose single-core cables from the pillar to the house; hang an unsheathed cable between the pillar and the house; splice in a buried box without protection against water.
- **Source:** AEA 90364-7-770 Ed. 2017: 770.4.1.1 (main line per AEA 95150 and calculated with the 770) and 770.16.3.1 (main panel at ≤ 2 m, Class II, IP54 outdoors, main line with double insulation). AEA 90364-7-771 Ed. 2006, table 771.12.I (outdoor overhead: IRAM 2263 aerial bundled cable or 2178 / 62266 / 2268 cables with support wire; underground: directly buried 2178 / 62266 / 2268; in a duct, NM 247-3 only as PE). **Not verified in a primary source:** each utility's requirements for the meter pillar and service connection (AEA 95150 and regulations), which are covered in [regulations-and-permits.md](regulations-and-permits.md) and [panels.md](panels.md).

### ELEC-CON-28: Cable for a split air conditioner
- **Rule:**
  - The split unit is supplied from its own circuit (see ELEC-ESP-11 in [special-installations.md](special-installations.md)).
  - The interconnection cable between the indoor and outdoor units is part of the equipment **only if it is up to 3 m long and joins one master unit with a single slave unit**. If it is longer or there are several units, it is part of the installation: it has the right insulation and cross-section, is protected against overload and short circuit, and is run like any other cable.
- **Why:** on site it is common to run 5 to 10 m of "taller" cable across the balcony, exposed and in the sun, because "it comes with the unit". That cable has no mechanical or UV protection, and if it is an NM 247-5 cord it is prohibited in fixed installations (ELEC-CON-3).
- **How:**
  - Run inside conduit or surface trunking: single-core NM 247-3 cables or sheathed cable.
  - Run outside the conduit (facade, balcony, drop to the outdoor unit): IRAM 2178-1 / 62266 sheathed cable, or the cable inside conduit or surface trunking rated for outdoor use with HIGH ("ALTA") UV protection (ELEC-CON-29).
  - Entry into the outdoor unit through a cable gland, with the cable forming a drip loop so water doesn't enter along the cable.
  - Cross-section and number of conductors (including the communication conductor and the PE): those in the manufacturer's manual, never less than what the AEA requires for the circuit.
- **Verify:** with the circuit switched off and verified dead: cable type printed, PE continuous up to the outdoor unit, no exposed single-core run, cable glands tightened.
- **Don't:** use flexible cord (*tipo taller*) as an interconnection longer than 3 m; tie the cable to the copper refrigerant pipe without its own wiring system on an exposed run; supply the outdoor unit from a balcony socket outlet.
- **Source:** AEA 90364-7-770 Ed. 2017, scope text on "equipo" (equipment) (p. 5, next to 770.1). It gives as an explicit example "los cables que interconectan las unidades compresoras y evaporadoras de equipos de aire acondicionado partidos" (the cables interconnecting the compressor and evaporator units of split air conditioners): up to 3 m and one slave unit are part of the equipment; otherwise, "formarán parte de la instalación" (they will be part of the installation). In this guide it is cited as 770.1 (definition of equipment), as in ELEC-ESP-11 and ELEC-CIR-10; confirm the page in your copy.

### ELEC-CON-29: Outdoors, terraces, garages and damp locations
- **Rule:**
  - Outdoors or in damp locations, wiring systems, boxes and panels have the IP rating that corresponds to the location: semi-covered IP44, outdoors IP54 and with water jets IP55, per ELEC-ESP-28 in [special-installations.md](special-installations.md).
  - Surface trunking exposed to the sun must have HIGH ("ALTA") UV protection.
  - In damp locations, exposed conduits, boxes and enclosures are spaced at least 0.01 m from the wall.
  - Outside conduit or surface trunking, only sheathed cable.
- **Why:** the sun degrades ordinary PVC in a few years: it cracks and leaves the cable exposed. Water that gets in through a badly sealed box or through the conduit itself ends up at a socket outlet terminal, with leakage to earth and RCD (*disyuntor* / *diferencial*) trips, or something worse.
- **How:**
  - Exposed outdoor conduits: zinc-plated or galvanized steel with threaded fittings, or insulating conduit rated for outdoor and UV exposure with fittings from the same system.
  - Boxes with cover and gasket, conduit and cable entries from below or from the sides, never from the top. A cable gland on every sheathed cable.
  - Avoid "U" sections where water collects. If they can't be avoided, use sheathed cable (ELEC-CON-2).
  - In garages, protect low runs against impact from vehicles (metal conduit or height).
- **Verify:** the IP rating is printed on the box and panel; the gaskets are fitted and all cover screws are in place; no indoor surface trunking is in the sun.
- **Don't:** use indoor surface trunking or boxes on a terrace; leave boxes with open knockouts; enter the box with the conduit from the top.
- **Source:** AEA 90364-7-770 Ed. 2017: 770.10.3.4 (spacing in damp locations; fittings for exposed work), tables 770.10.III and 770.10.IV (surface trunking: minimum IP and UV protection), 770.10.3.6.3 (conduits in a "U"). IP values by location: ELEC-ESP-28 in [special-installations.md](special-installations.md), with its own source.
### ELEC-CON-30: Circuits for high continuous loads (water heater (*termotanque*), oven, cooktop (*anafe*), EV charger)
- **Rule:** these loads run for hours at full current. Their cable is chosen with the nameplate current (IB), corrected for the actual temperature and grouping (ELEC-CON-8), with IB ≤ In ≤ Iz, and the voltage drop is checked. Each one goes on its own circuit, per [special-installations.md](special-installations.md).
- **Why:** a TUG circuit is meant for loads that are plugged in for a while. A water heater, a cooktop or a car charging all night take the cable to its maximum temperature for hours, and any loose splice or terminal becomes a hot spot.
- **How:** guidance values (single-phase 220 V, single-core cables in conduit, a single circuit in the conduit, 40 °C):

| Load (assumed figure) | IB = P / 220 V | Guidance cross-section | Iz (table) | In | See |
|---|---|---|---|---|---|
| Water heater 1.5 kW | 6.8 A | 2.5 mm² | 21 A | 10 A or 16 A | ELEC-ESP-6 |
| Electric oven 3.5 kW | 15.9 A | 2.5 mm² | 21 A | 16 A | ELEC-ESP-12 |
| Induction cooktop 7 kW | 31.8 A | 6 mm² | 36 A | 32 A | ELEC-ESP-12 (over 20 A: fixed connection) |
| 32 A EV charger (≈ 7 kW) | 32 A | 6 mm² minimum; 10 mm² if there is temperature or grouping | 36 A / 50 A | 32 A | ELEC-ESP-17 |

  - **Correction example:** cooktop on 6 mm² with the conduit running through a roof space at 50 °C: Iz = 36 × 0.82 = 29.5 A < 32 A. Does not comply: 10 mm² is needed (50 × 0.82 = 41 A).
  - **16 A oven sharing a conduit:** with one other circuit, Iz = 21 × 0.80 = 16.8 A ≥ 16 A, complies. With two more, Iz = 14.7 A < 16 A, does not comply. Also, special-use and general-purpose circuits don't share a conduit (ELEC-CON-10).
  - Charger in a garage 40 m from the panel (distribution board): voltage drop with 6 mm² = 6.5 × 32 × 0.040 = 8.32 V → 3.8 %. Does not meet the 3 %. With 10 mm²: 3.8 × 32 × 0.040 = 4.86 V → 2.2 %. With 16 mm²: 2.4 × 32 × 0.040 = 3.07 V → 1.4 %. Subtract the sub-main voltage drop: in an apartment (*depto*) under the 771, the final circuit cannot exceed 2 % from its sub-panel (TS, *tablero seccional*), so 16 mm² is needed.
- **Verify:** nameplate data recorded in the technical report; corrected Iz ≥ In; terminals tightened to the manufacturer's torque; thermography under load after one hour of use.
- **Don't:** plug the water heater or the charger into a TUG circuit; use 10 A plugs for loads above 10 A; size with the "catalog" power without looking at the nameplate.
- **Source:** current-carrying capacity and factors: AEA 90364-7-770 Ed. 2017, table 770.12.I, and AEA 90364-7-771 Ed. 2006, tables 771.16.I and 771.16.II.a. Voltage drop: 770.15.6 and 771.13 b). Dedicated circuits, protection and RCDs (*diferenciales*) for each load: [special-installations.md](special-installations.md) (AEA 90364-7-722 Ed. 2024 for electric vehicles). The powers in the table are example assumptions: use the equipment nameplate.

### ELEC-CON-31: Rewiring old installations (iron conduit without PE, cloth- or rubber-insulated cables)
- **Rule:** every circuit you work on ends up with a continuous PE to every box and with present-day certified cables. Cables with cloth, rubber or hardened PVC insulation are replaced completely, from box to box: they are not spliced to new cable. The existing conduit is reused only if it meets all of this:
  - it is continuous;
  - it has no corrosion or burrs that could damage the cable;
  - its boxes are accessible;
  - its diameter is enough for the new cables **plus the PE** per the tables in ELEC-CON-12.

  If it does not comply, new conduit is installed, embedded or exposed (ELEC-CON-16).
- **Why:** without a PE, an exposed conductive part with an insulation fault stays live until someone touches it. The RCD (*disyuntor* / *diferencial*) trips, but only once the current is already flowing through the person. Cloth and rubber cables more than 40 years old have cracked insulation: when you move them to pull in the PE, they finish breaking inside the conduit.
- **How:**
  1. Switch off, lock out and verify absence of voltage on everything you are going to touch ([site-safety.md](site-safety.md)).
  2. Survey: open the boxes, identify circuits and measure the insulation of whatever you plan to keep (with the precautions of ELEC-CON-20).
  3. Remove the old cables. Use one as a guide only if it comes out without forcing; if it gets stuck, use a fish tape. If the conduit is blocked, crushed or corroded, that run must be replaced.
  4. Pull the new circuit with its green-yellow PE in the same conduit (ELEC-CON-10), with the cross-section from ELEC-CON-6.
  5. Connect metal conduits and boxes to the PE by a branch connection: the iron conduit does not replace the PE.
  6. Throw out any orange conduit, flexible cord (*tipo taller*) and solid wire you find (ELEC-CON-3).
  7. Give the owner a report on the condition of what was not touched, with the safety conditions.
- **Verify:** PE continuity to every earth terminal, insulation of each circuit and RCD test (see [testing-and-commissioning.md](testing-and-commissioning.md)). The typical faults in old installations are in [troubleshooting-common-cases.md](troubleshooting-common-cases.md).
- **Don't:**
  - use the iron conduit as the PE;
  - run the PE on the outside, stuck to the wall and without a wiring system;
  - make a jumper between earth and neutral at the socket outlet;
  - splice new cable to cloth cable inside the conduit or in a covered box;
  - force new cable into an already full old conduit "because it went in with force".
- **Source:** AEA 90364-7-770 Ed. 2017:
  - 770.4.1.2: modifications and extensions comply with AEA 90364, and the installer gives the owner "una información fehaciente referida al estado de las instalaciones eléctricas existentes" (reliable information on the condition of the existing electrical installations);
  - 770.10.3.2: metal wiring systems do not replace the PE;
  - 770.14.4.5: the PE runs through the entire installation;
  - 770.10.3.8.2 a), 770.10.1 and tables 770.10.VII to IX.

  **Not verified in a primary source:** the criterion of always replacing cloth or rubber cables. It is site practice; the AEA has no specific clause that was consulted.

## What this guide does not replace

- The **design, calculation and signature** are done by a licensed professional or licensed electrician (*matriculado*) with the relevant competence, depending on the jurisdiction (see [regulations-and-permits.md](regulations-and-permits.md)). That professional also decides whether the 770 or the 771 applies in each unit.
- The **utility (distribution company)** decides the service connection, the meter pillar (*pilar*), the meter panel, the short-circuit current it reports and everything before the meter.
- The **municipality, fire department or local authority** may require more: for example, LS0H in buildings, certified firestop sealing or metal conduits in certain uses.
- AEA and IRAM standards are paid: this guide summarizes and cites, but the exact number for a project is taken from the current text. Check AEA 90364-7-770 Ed. 2026 and the corrigenda to the 771 at aea.org.ar.
- No step in this guide is done live. Before touching cables or boxes, switch off, lock out, post signs and verify absence of voltage ([site-safety.md](site-safety.md)).
