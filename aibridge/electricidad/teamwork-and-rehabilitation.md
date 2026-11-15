---
title: Rehabilitating an installation with leakage and short circuits as a team (diagnosis, sectioning, organization, group lockout)
scope: full repair ("fixing it from the ground up") of an existing low-voltage installation in Argentina (house, apartment, shop) that has earth leakage, short circuits, RCD trips and a panel that grew by patches, when 2 to 6 people work at the same time; includes the ordered diagnosis, the sectioning strategy, team organization, group lockout/tagout and a day-by-day plan for a real case
when_to_use: "salta el disyuntor y nadie sabe por qué" (the RCD trips and nobody knows why); a panel with many added MCBs, several switched off or labeled "no usar" (do not use); a crew is put together to redo an installation; the work has to be split among several technicians without anyone being exposed; you have to decide what gets fixed first and what stays powered meanwhile; someone left the site with the key to their padlock; you need to put together a work permit, a lockout tag or a closing checklist
related: [README.md, site-safety.md, surveys-and-drawings.md, troubleshooting-common-cases.md, testing-and-commissioning.md, reviewing-a-panel.md, protection.md, panels.md, earthing.md, special-installations.md, conductors-and-conduits.md, grades-and-circuits.md, regulations-and-permits.md, buildings.md]
as_of: 2026-11-15
sources: [Decreto 911/96 arts. 2, 52, 54, 57, 75, 76, 78, 79, 86, 87, 112, 214-227 (text on argentina.gob.ar, art. 79 reread 2026-11-15), Decreto 351/79 Anexo VI cap. 14 (lockout 1.1.4; training and the person-in-charge role 1.2.2 and 1.2.3, numbering inferred; restoring service 2.1.3 c), numbering inferred; per site-safety.md; applies to establishments and buildings in use, not to construction), Ley 24.557 arts. 2, 31 and 43 (updated text on argentina.gob.ar, consulted 2026-11-15), Res. SRT 3068/2014, Res. SRT 61/2023, Res. SRT 35/98, Res. SRT 503/14, Res. SRT 900/2015, SRT Manual de Buenas Prácticas TST 2023 (good-practice manual for live work), AEA 90364-7-770:2017 Corr. 1 2018 (770.14.3.2, 770.16.5.1, 770.16.5.4, 770.19.5.2.1), AEA 90364-7-771 (annex 771-B.7), AEA 90364-7-704 ed. 2026 (content not verified), AEA 90364-7-702:2018, IEC 61008-1, IEC 60364-6, IEC 61010-1, IEC 61243-3, OSHA 29 CFR 1910.147 (c)(5)(ii), (d)(6), (e)(3), (f)(3), (f)(4) and 1910.333(b)(2) (reread 2026-11-15; reference, not law in Argentina), NFPA 70E art. 120 (reference; not consulted in this version), Master Lock 498A (group lockbox) and S2391 (lockout device for pin-out DIN MCB), data sheets consulted 2026-11-15]
---
# Rehabilitating an installation with leakage and short circuits, working as a team

This guide is for the job where the installation "half works": the RCD (*diferencial*) trips, there are MCBs (*térmicas*) added
at the very bottom with handwritten labels, circuits switched off "because they made it trip", taped splices in the garden, and
it has to be left in good shape. When one person fixes one circuit, [site-safety.md](site-safety.md) is enough.
When three or six people work at the same time on the same panel (distribution board, *tablero*), risks appear that a single
person does not have: someone energizes while another still has a hand in a box, a coworker runs an insulation test at 500 V on
a cable that someone else is stripping, or someone goes home with the padlock key in their pocket.

Each rule has a stable ID (`ELEC-EQU-n`) so that the agent, a site report or a work permit can cite it.
**Guiding principle:** in this guide there is no live work. The only tasks with the installation energized are
switching operations from the front with the inner cover (dead front, *contratapa*) in place and some measurements, and they
have their own conditions (ELEC-EQU-32). The five golden rules and individual lockout are in [site-safety.md](site-safety.md)
(ELEC-SEG-3 to 7); here we add what changes when there are several people. A locked-out MCB protects the field cable, not the
inside of the panel: to work inside the panel, cut the supply further upstream (ELEC-EQU-31).

The agent keeps the map and the progress with the tool `gateway electricidad plan ...` (contract, schema of
`survey.json` and symbols in [surveys-and-drawings.md](surveys-and-drawings.md), ELEC-PLA-17 to 20): one file
per job in `/workdir/electricidad/<job>/`, from which come the drawing, the single-line diagram (*unifilar*), one sheet per
circuit for each technician and the progress table. The commands in this guide follow that contract; if the tool does not
respond in the installation, the agent still builds and updates the JSON, lists what is pending in text and reports that it
could not draw. The calculations (current, voltage drop, cross-section, coordination, earth) are done with
`gateway electricidad current|drop|size|coordinate|earth`, not from memory.

## Quick reference
| Situation | Rules |
|---|---|
| We arrive at a house with an RCD (ID) that trips and a patched-up panel: where do I start? | ELEC-EQU-1, 2, 3, 6 |
| I suspect the pool, the gate or the garden lights | ELEC-EQU-4 |
| I switch off the MCB and there is still voltage, or the RCD trips with a load from another circuit | ELEC-EQU-5, 24, 25 |
| We have to work inside the panel (neutrals, devices, dismantling): where do I cut from? | ELEC-EQU-31 |
| We lift the neutrals: label, reconnect, tighten | ELEC-EQU-34 |
| Measuring live (leakage clamp meter, RCD trip, voltage at terminals) | ELEC-EQU-32 |
| Do I fix circuit by circuit or redo the panel first? | ELEC-EQU-7, 8 |
| The fridge, the water pump or the gate cannot be left without power | ELEC-EQU-9 |
| Energizing one part while others keep working; moving from general lockout to per-circuit lockout | ELEC-EQU-33 |
| Do I repair the section or rewire? | ELEC-EQU-10 |
| When do I consider a circuit finished? | ELEC-EQU-11 and "Circuit closing checklist" |
| There are several of us: who is in charge, who cuts, who energizes | ELEC-EQU-12, 13, 17 |
| Splitting the work and tracking progress | ELEC-EQU-8, 14 |
| Start of the day, communication, end of the workday, shift change | ELEC-EQU-15, 16, 18, 19 |
| Lockout with several padlocks, group lockbox | ELEC-EQU-20, 21 |
| Someone left with the key to their padlock | ELEC-EQU-22 |
| The lockout device does not fit the DIN MCB | ELEC-EQU-23 |
| Verifying absence of voltage when there are several of us | ELEC-EQU-25 |
| Generator set, UPS, solar panels, another panel, capacitors | ELEC-EQU-26 |
| One person runs an insulation test while others work | ELEC-EQU-27 |
| Occupied house: kids, pets, pool, neighbors | ELEC-EQU-28 |
| Ladders, drilling, dust and water near the panel | ELEC-EQU-29 |
| Can someone work alone? There are two of us and one is at the back of the property | ELEC-EQU-35 |
| Heat, long workdays, pressure to restore power today | ELEC-EQU-36 |
| Accident, first aid, ART (workers' compensation insurer), independent technicians without ART | ELEC-EQU-30 |
| Worked case: the house with the panel from the photo, day-by-day plan for 3 people | "Case: the house with the panel that grew by patches" |
| Work permit, lockout tag, checklist | "Templates" |

## Applicable regulations and references (status as of 2026-11-15)
| Norm | What it contributes to this guide | Status |
|---|---|---|
| Decreto 911/96, art. 79 | Dead-work procedure with two roles. a) At the supply points, the **person responsible for the work** (*responsable del trabajo*) isolates, locks, places the "Prohibido Maniobrar" (do not operate) sign with their name and carries out the lockout (a I-IV: visible break, verify absence of voltage, earth and short-circuit the access points, put up signs). b) At the workplace, the **person responsible for the task** (*responsable de la tarea*) repeats those steps and also checks for voltage on the neutral. c) The person responsible for the task restores service only after personally checking that the earths they placed, the tools, the leftover material and the signs have been removed, that the personnel have moved away and that the insulation test was done (c I-IV). d) Then they unlock the isolators and remove the signs. The decree does not define each role separately | In force (construction). Text reread on argentina.gob.ar on 2026-11-15 |
| Decreto 911/96, arts. 75 and 87 | Art. 75: minimum distances to uninsulated live parts (ELEC-SEG-8). Art. 87: periodic inspection; the repair restores the original characteristics; a trip with no known cause requires inspection before resetting | In force |
| Decreto 351/79, Anexo VI cap. 14 | Lockout (*consignación*) (1.1.4), training and the person-in-charge role (1.2.2 and 1.2.3, numbering inferred), restoring service (2.1.3 c), numbering inferred). Applies to establishments and buildings in use; on construction sites Dec. 911/96 governs (its art. 2 excludes 351/79 from construction) | In force; details and quotes in [site-safety.md](site-safety.md) |
| Res. SRT 3068/2014 | Live work up to 1 kV: a separate trade, not done by this crew | In force |
| Res. SRT 61/2023 | Safety measures for work at height (construction) | In force |
| Ley 24.557, arts. 31 and 43 | The employer reports accidents to the ART and the SRT and keeps an accident record per establishment; benefits start with the report | In force; text consulted on argentina.gob.ar |
| Res. SRT 35/98 | Safety coordination between the main contractor and subcontractors on the same site | Cited as in force by Res. SRT 61/2023 (per site-safety.md) |
| AEA 90364-7-770 / 7-771 / 7-702 | 30 mA RCD on final circuits, how to group circuits per RCD, upstream RCD of up to 300 mA (selective recommended), insulation minimum 1 MΩ at 500 V, swimming pools | Mandatory; editions in [regulations-and-permits.md](regulations-and-permits.md) |
| AEA 90364-7-704 ed. 2026 (or annex 771-B.7 where it was not adopted) | Construction site installation: the temporary essential-service panel | See ELEC-NOR-5; content of 704 not verified |
| OSHA 29 CFR 1910.147 and 1910.333 (USA) | Group lockout (f)(3), shift change (f)(4), removal of another person's padlock (e)(3), requirements for padlocks and tags (c)(5)(ii) | **Not law in Argentina.** Used as a good-practice reference because it is the most detailed freely available text on group lockout |
| NFPA 70E (USA), art. 120 | Electrically safe work condition; distinguishes "simple" and "complex" lockout (several sources, several crews, more than one shift) with one person in charge and a written plan | **Not law in Argentina.** Reference. Current edition and numbering: **not verified in this version** |

No specific SRT resolution on group lockout in residential low voltage was found: the personal padlock, group lockbox and DIN
lockout device are international practice that this guide adopts as a site rule. No Argentine text was found either that
requires the person responsible for the work and the person responsible for the task to be one and the same: this guide does
that by its own criterion on small jobs (ELEC-EQU-12).

## Rules

### Ordered initial diagnosis

### ELEC-EQU-1: Before touching anything, a circuit map and a photo of the current state
- **Rule:** no repair work starts without a survey (as-found survey, *relevamiento*): what protective devices there are, which circuit feeds each outlet point (*boca*), what is switched off and why, and a sketch (*croquis*) per floor with rooms and outlet points. If there are no drawings, sketch it by eye; that is enough to work.
- **Why:** in a panel that grew by patches the labels lie or are missing, there are circuits "nobody knows what they feed" and neutrals that pass from one to another. Without a map, each technician discovers the same things on their own and nobody can be sure what they cut.
- **How:**
  1. Photos of the panel (front, labels, incoming supply, busbars), of the main panel at the meter pillar (*pilar*) and of each visible outdoor box (ELEC-REV-1, ELEC-REV-3). Read the photo with [reviewing-a-panel.md](reviewing-a-panel.md).
  2. Interview: when does it trip (when it rains?, when something is switched on?, at night with the garden lights?), what was added and when, which circuits were switched off, whether there is a generator set, UPS, solar panels or an electricity-dependent person (ELEC-NOR-19).
  3. `gateway electricidad plan new <job>` and the agent loads what is known from the photo and the conversation (protective devices, labels, floors). Source `"by-eye sketch"`.
  4. Circuit identification (ELEC-PLA-11 and 13): with the inner cover in place (if the panel has none, first fit one, with the panel cut off upstream: ELEC-REV-8, ELEC-EQU-31), the person in charge switches off **one** MCB at a time, with the others on, standing to one side (ELEC-SEG-29), and the others go around with a plug-in tester that shows phase, neutral and earth, or with a lamp, operating each switch, and write down which outlet point goes dead. This is a switching operation from the front, not work on live parts.
     - **MCBs found open are not closed to identify them:** they may be open because of a short circuit or a leak, and closing them energizes a fault while coworkers go around the house and the garden. They get a "FUERA DE SERVICIO" (out of service) tag from day one and their circuit is identified dead, by continuity or with a tone generator, after testing insulation (ELEC-PLA-11 step 5, ELEC-EQU-2).
     - **Signs of crossed circuits:** an outlet point that goes dead with two different MCBs, one that does not go dead with any, a light that stays dim, or a socket outlet where the tester still shows phase with its MCB open are marked `status: doubtful` with both circuits in `note` (ELEC-PLA-15). With the phase from one circuit and the neutral from another, the outlet point goes dead with either of the two MCBs, and in a single pass it looks like it belongs to the first one switched off: that is why each MCB is tested against **all** outlet points, not until you find "its own". While a circuit has `doubtful` outlet points, that circuit stays under the panel cut-off (ELEC-EQU-24).
     - **Light switch that breaks the neutral:** with the switch off, the lampholder stays at phase. If a light goes off with the switch but the tester or a non-contact detector shows something odd, it is noted as `doubtful`. Nobody replaces a luminaire trusting the switch (ELEC-EQU-25).
     - What is identified this way is a map, not a verification of absence of voltage (ELEC-PLA-16).
  5. Sketch per floor (rooms as approximate rectangles, outlet points with their height; ELEC-PLA-7 and 8) → the agent fills in `rooms`, `points` and `runs`; `plan validate` shows what is missing; `plan draw` and `plan single-line` produce the sheets for the job. The agent can list the `doubtful` points so the person in charge decides how to resolve them.
- **Verify:** each outlet point has a circuit assigned or appears as "unidentified"; each protective device has a circuit or appears as "unused"; no MCB that was open has been closed; `plan validate` with no reference errors.
- **Don't:** start "testing" by opening boxes before having the map; trust a handwritten label without checking it; operate MCBs on a panel without an inner cover with your hand near live terminals; switch on an MCB that was off "to see what it feeds".
- **Source:** Decreto 911/96 art. 78 a) (identify the conductor or installation before working); ELEC-SEG-1, ELEC-SEG-22 and ELEC-SEG-29 (do not close onto an undiagnosed fault); ELEC-PLA-11, 13, 15 and 16. Identification and sketch method: site practice, **not verified in a primary source** as normative text.

### ELEC-EQU-2: Test insulation circuit by circuit, with loads disconnected and neutrals separated
- **Rule:** with the whole panel locked out **from upstream** (this is work inside the panel: ELEC-EQU-31), test each circuit separately with a megohmmeter (megger): phase-PE, neutral-PE and phase-neutral, at 500 V DC, with electronic loads disconnected and each circuit's neutral lifted from its terminal and labeled (ELEC-EQU-34). Record the value in the survey.
- **Why:** tested together, a bad circuit hides among the good ones (the parallel of 26 circuits gives a number that does not say which one fails). Separating the neutrals is what lets you see a neutral touching earth or joined to another circuit's neutral.
- **How:** procedure and table of minimums in [testing-and-commissioning.md](testing-and-commissioning.md) (ELEC-MED-4) and search by sections in [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-4). As a team, in sequence and by groups: (1) the person in charge, alone at the panel, lifts and labels the neutrals; (2) another person disconnects the loads of a group of circuits with the sheets in hand and announces "grupo X libre" (group X clear); (3) measurement window for that group: nobody touches its conductors or the terminal block, the person testing announces, waits for confirmation and lets it discharge (ELEC-EQU-27); (4) move on to the next group. Record: the circuit's `measurements` with date, type `insulation`, value in MΩ and `ok`.
- **Verify:** each circuit has its three readings; those that read low or far below similar circuits are set to status `fault`.
- **Don't:** megger with LED drivers, power supplies, sensors or the gate motor connected; measure "everything together from the main".
- **Source:** AEA 90364-7-770:2017 Corr. 1 (2018), 770.19.5.2.1 (1 MΩ at 500 V DC, aligned with IEC 60364-6), per ELEC-MED-4.
### ELEC-EQU-3: A single RCD (*disyuntor* / *diferencial*) that trips: separate the sum of leakages from the hard fault
- **Rule:** when a single RCD (*diferencial*) protects the whole house, distinguish two problems that give the same symptom: (a) a circuit with a hard earth fault (low insulation, trips even when it is alone) and (b) the sum of small leakages from many healthy circuits and appliances that together reach the threshold. The first is fixed in the circuit; the second, by spreading circuits across several RCDs (ID).
- **Why:** a 30 mA RCD can trip from half its rated value (15 mA). With twenty-odd circuits, electronics, LEDs and a damp outdoor area, the margin is used up; any transient completes the trip. If you only look for "the culprit", it never shows up.
- **How:**
  1. Megohmmeter results (ELEC-EQU-2): circuits with low insulation are hard faults.
  2. With the installation already sectioned, or with the healthy circuits, the person in charge measures with a leakage clamp meter (mA, clamping phase and neutral) the residual current of each circuit with its usual load (ELEC-DIA-6). This is a live measurement and follows ELEC-EQU-32: never on a panel (distribution board, *tablero*) without an inner cover (dead front, *contratapa*); preferably where the circuit leaves with the inner cover in place or at the load, with a separable-conductor adapter.
  3. Add up per group: what hangs from one RCD should not exceed 30 % of its IΔn (about 9 to 10 mA on a 30 mA RCD).
- **Verify:** no circuit with a hard fault stays connected; the leakage measured per RCD is well below 0.3 × IΔn and is recorded.
- **Don't:** replace the 30 mA RCD with a 300 mA one or one "bigger in amps"; remove the PE from the appliances so it stops tripping.
- **Source:** trip between 0.5 and 1 IΔn: IEC 61008-1 (per ELEC-DIA-6). 0.3 IΔn criterion: IEC 60364-5-53 per ELEC-PRO-11, with the exact clause **not verified in a primary source**.

### ELEC-EQU-4: Outdoor areas, pool and gate: the usual suspects
- **Rule:** in an installation with leakage, first check what gets wet: garden and front lights, outdoor socket outlets, porch, pool pump and pool panel, gate motor and control unit, cistern pump, boxes buried or in the subfloor, and any splice made with tape.
- **Why:** these are the places with water, soil, chlorine, sun and knocks; they are also usually the last things added, with single-core cable buried without conduit, boxes without an IP rating and "temporary" splices that are years old. In the panel they show up as the MCBs (*térmicas*) of another brand in the last row.
- **How:** megger each one separately; open first the lowest or most exposed box on the run; look for boxes full of water, connectors green with oxide, cable with the sheath cracked by the sun, luminaires with a worn-out gasket. Motors (pump, gate): test the motor separately from the cable to know which of the two fails. Design rules for what gets redone: ELEC-CIR-11, ELEC-ESP-8, ELEC-ESP-9, ELEC-ESP-28, ELEC-ESP-30, ELEC-CON-19.
- **Verify:** each outdoor circuit has its insulation reading in dry weather and, if possible, after rain or watering.
- **Don't:** "dry it with a hair dryer and close it" without changing the box or the IP; leave the pool pump plugged into an extension cord in the meantime.
- **Source:** ELEC-DIA-4 (outdoor areas first, source: Miravalles, *Ingeniería Eléctrica* 336, 2018); AEA 90364-7-770:2017 770.6.6 a) (recommends independent circuits for outdoor use) and 7-702:2018 (swimming pools), per ELEC-ESP-8 and ELEC-ESP-30.

### ELEC-EQU-5: Look for shared or crossed neutrals before trusting the per-circuit cut-off
- **Rule:** until it has been checked that each circuit has its own neutral, returning through its two-pole MCB and its RCD, nobody works with only the circuit's MCB open: the panel cut-off is locked out (ELEC-EQU-24). Checking the neutrals is part of the diagnosis.
- **Why:** in a patched-up panel it is common for an added circuit to "take the neutral from the box next door". Then, with circuit A's MCB open, its neutral is still joined to circuit B in use: whoever works on A has a conductor carrying current and with voltage to earth. That crossing also makes the RCD trip with any load.
- **How:** there are two different kinds of crossing and each is found with its own method. Start with the circuits that have `doubtful` outlet points (*bocas*) from the identification (ELEC-EQU-1, ELEC-PLA-15).
  - **(a) Neutrals joined to each other, dead:** with the panel cut off upstream (ELEC-EQU-31), the neutrals lifted, labeled and each end insulated (ELEC-EQU-34), test each neutral against **the set** of the others temporarily jumpered together: 26 measurements, not the 325 pairs of a matrix. If one shows continuity, split the set in halves until you find which one. Add the neutral-PE insulation (ELEC-DIA-5, ELEC-TAB-16).
  - **(b) Phase of one circuit with the neutral of another:** the most common case (the added outlet point takes the phase from A and the neutral from B). With the loads disconnected, (a) does not see it, because N_A and N_B do not touch. It is found by energizing one circuit at a time: only for circuits that already tested good for insulation, with the loads reconnected, **only that circuit's neutral** connected, the other neutrals lifted with their ends insulated, inner cover in place, nobody working on the installation and an announcement with confirmation (ELEC-EQU-16). The person in charge closes only that MCB and the others test all its outlet points. An outlet point that does not work with its circuit alone, or that works but trips an RCD of another group once sectioned, returns through someone else's neutral. While the test lasts, that lifted foreign neutral is live through the load: that is why the ends are insulated and nobody touches the panel. Dead alternative for a single outlet point: with the MCB open and a resistive load connected at the outlet point (incandescent or halogen lamp), continuity between the circuit's phase and the set of foreign neutrals.
  - Mark the crossings in the survey (*relevamiento*) in the `notes` of both circuits and treat them as a single work package until they are separated.
- **Verify:** each neutral tested against the set (a); each circuit tested with its neutral alone (b); no unresolved `doubtful` outlet point; crossed circuits identified and grouped.
- **Don't:** jumper neutrals of different RCDs "so it doesn't trip"; think that a two-pole MCB protects the person working if the neutral is shared downstream, in a box; do test (b) with loose uninsulated neutrals or with someone at the panel; accept the neutrals as good just because measurement (a) read open.
- **Source:** ELEC-DIA-5, ELEC-TAB-16 and ELEC-PLA-15 (RCD operating principle, IEC 61008-1; AEA 770.16.5.1 two-pole disconnection of each circuit). Methods (a) and (b): diagnostic practice of this guide, **not verified in a primary source**. The requirement of a dedicated neutral per circuit as a literal AEA clause: **not verified in a primary source**.

### Rehabilitation strategy

### ELEC-EQU-6: Priority by risk: electric shock, then fire, then service
- **Rule:** order the work by risk to people: (1) electric shock, (2) fire, (3) continuity of service. Whatever can kill someone is fixed or taken out of service on the first day, even if something is left without power.
- **Why:** with several people and many open fronts, the temptation is to start with what bothers the owner most ("get the garden lights back"). The fault that kills gives no warning.
- **How:**
  - **Shock (first):** accessible live parts in the panel (no inner cover, bare busbars, loose cable), circuits outside the RCD, outdoor areas and pool with low insulation, exposed conductive parts without PE, stripped cables in walkways. They are cut off and locked out with a "FUERA DE SERVICIO" (out of service) tag until repaired.
  - **Fire (second):** MCB larger than what the cable allows (ELEC-REV-11, ELEC-PRO-4), loose or overheated terminals, taped splices inside ceilings, melted socket outlets (ELEC-DIA-11, ELEC-DIA-12).
  - **Service (third):** trips from the sum of leakages, healthy circuits that were switched off, labels, tidiness.
- **Verify:** at the end of the first day, no identified shock risk remains energized.
- **Don't:** leave a circuit with low insulation in service "until we get to it"; reconnect circuits the owner switched off without testing them.
- **Source:** Decreto 911/96 art. 87 (correct abnormalities; a trip with no known cause requires inspection before resetting). The order shock > fire > service is a technical criterion of this guide, consistent with ELEC-DIA-17 and ELEC-REV-22; **not verified in a primary source** as a normative order.

### ELEC-EQU-7: Section first: several RCDs (*diferenciales*) and the outdoors separate
- **Rule:** before repairing circuit by circuit, redo (or reorganize) the panel with several 30 mA RCDs by groups, with pool and outdoor areas on their own RCDs, and, if it makes sense, an outdoor sub-panel (TS, *tablero seccional*). Afterwards, each fault takes only its group out of service and is searched for in a small universe.
- **Why:** with a single RCD for everything, each test turns off the house and a fault in the garden leaves you without a fridge. Sectioning restores service to the healthy part the same day, reduces the sum of leakages per RCD (ELEC-EQU-3) and lets the technicians work on groups that are cut off separately.
- **How:**
  1. Group by zone and by risk, not "all the lights together": a trip should not leave the whole house in the dark (ELEC-PRO-11). Typical: bedrooms; living room and kitchen (fridge on an RCD without outdoor circuits; type A if there is an inverter or a lot of electronics, ELEC-PRO-9); service area (laundry, garage); outdoor areas; pool alone; gate and water pump.
  2. If an RCD remains upstream of the 30 mA ones, the AEA allows it (to protect the line) with an IΔn of up to 300 mA and recommends that it be selective (S). For real selectivity (discrimination), this guide requires it to be type S with an IΔn of at least 3 times the one below (practical criterion). An instantaneous 30 mA upstream is no good: it has to go (ELEC-PRO-12).
  3. Outdoor sub-panel near the pool, porch and gate: it shortens runs, takes the dampest circuits out of the house and gives its own cut-off point. The line that feeds it has its protection in the house panel.
  4. In three-phase, spread the groups across phases and measure the balance (ELEC-CIR-16).
  5. 20 % spare capacity and a busbar comb (*peine*) instead of cable daisy chains (ELEC-TAB-7, ELEC-TAB-13).
- **Verify:** `plan single-line` shows each circuit under a 30 mA RCD; no RCD with outdoor circuits is shared with the fridge; `plan validate` with no "there is no 30 mA RCD upstream" error.
- **Don't:** leave the original 4P 30 mA RCD above the new ones; mix the pool and the indoor lighting on the same RCD.
- **Source:** AEA 90364-7-770:2017, note 1 of 770.16.5.4 (one RCD per circuit or grouping several) and 770.14.3.2 b) (upstream RCD up to 300 mA, selective recommended), per ELEC-PRO-11 and ELEC-PRO-12; 770.6.6 a) (independent circuits for outdoor use: the AEA **recommends** it), per ELEC-ESP-30. Separating the pool and outdoor areas onto their own RCDs when rehabilitating an installation with leakage is a **criterion of this guide**, stricter than the AEA (for the pool, 7-702 also has its own requirements: ELEC-ESP-8).

### ELEC-EQU-8: Work packages that can be cut off independently
- **Rule:** divide the job into work packages: one circuit, or a group of circuits that share boxes or neutrals, that can be left dead with its own cut-off and locked out without affecting the others. Each package has only one assignee at a time and its sheet.
- **Why:** if two people work on packages that share a junction box or a neutral, one person's cut-off does not protect the other. A well-defined package is what makes it possible to work in parallel.
- **How:**
  1. From the survey: circuits that share a box, a conduit with conductors from several circuits, or crossed neutrals (ELEC-EQU-5) go into the same package or are separated first.
  2. `gateway electricidad plan sheets /workdir/electricidad/<job>/survey.json` generates one sheet per circuit (or `--tech "Technician B"` for one person's sheets): isolated drawing with the rest dimmed, table of outlet points, **protective device to lock out**, pending measurements and a lockout checklist (ELEC-PLA-19). For a separate drawing of one or two circuits: `plan draw ... --only C7,C8`.
  3. Assignment in the survey: the circuit's `assigned_to` field (name or initials; no national ID numbers or phone numbers in the file).
  4. While the panel is not yet sectioned and the neutrals are not checked, the package is cut off from the panel cut-off (ELEC-EQU-24): in that phase work is done by zones, everyone under the same group lockout.
  5. A package is field work (cables, boxes, outlet points). What is done inside the panel (connecting, disconnecting, separating neutrals) is not part of any package: the person in charge schedules it with the panel cut off upstream (ELEC-EQU-31).
- **Verify:** no box on the drawing appears in two packages assigned to different people; each sheet says what gets locked out.
- **Don't:** "you do the front lights and I'll do the front socket outlets" if they share boxes; reassign a package without the previous person removing their padlock.
- **Source:** OSHA 1910.147 (f)(3)(ii)(A) to (C) (responsibility for a defined group of workers and coordination when there are several crews), as a reference; ELEC-PLA-19 (isolated sheet per circuit). Division into packages: site management practice, **not verified in a primary source** in Argentina.

### ELEC-EQU-9: Essential service runs on a protected temporary circuit
- **Rule:** if there are loads that cannot be left without power while work is underway (fridge, water pump, gate, medical equipment), they are fed by a temporary circuit independent of what is being repaired: with its own MCB, its own 30 mA RCD, its PE and suitable cable, like a construction site installation.
- **Why:** if the fridge hangs from a circuit under repair, someone is going to ask "switch the MCB on for a while", and that breaks everyone's lockout.
- **How:**
  1. A temporary panel (enclosure with PIA + 30 mA RCD + socket outlets with earth) fed from a point that is **not** cut off during the work, that is, upstream of the point where the house is locked out. The panel at the meter pillar (*pilar*) of a dwelling usually has a single switch, with no free outgoing way, and its incoming terminals come live from the meter, which the installer cannot cut off (ELEC-SEG-34). Options, in order:
     - **Branch at the meter pillar:** in a separate box next to the pillar, downstream of the pillar switch, two outgoing ways: one protective device for the line to the house (it will be the house cut-off point for work inside its panel, ELEC-EQU-31) and another with its PIA and its 30 mA RCD for the temporary circuit. It is installed in a short, scheduled window, with the pillar switch open and locked, the incoming terminals covered with an insulating shield, PPE (ELEC-EQU-32) and nobody else working; if the utility's (distribution company's) regulations do not allow touching the pillar or the terminals cannot be covered, the cut-off is coordinated with the utility.
     - **Portable generator set** with a 30 mA RCD and its earth rod (*jabalina*), which feeds **only** the temporary circuit and is never connected to the house installation (ELEC-SEG-21).
     - In three-phase, record which phase the temporary circuit comes from.
  2. Certified extension cords, without splices, out of walkways and water (ELEC-SEG-14, ELEC-SEG-15, ELEC-TAB-21).
  3. Label it "PROVISORIO - CON TENSIÓN" (temporary - live) and mark it on the drawing; everyone knows that this cable and the pillar branch are live, and that the house cut-off does not cut them.
  4. Gate: almost all have a manual release; tell the owner to operate it by hand while its circuit is redone.
  5. Electricity-dependent person: their equipment has a guaranteed supply (temporary circuit, the equipment's own UPS or a battery) and a plan if everything is cut off (ELEC-NOR-19).
- **Verify:** the temporary circuit has an RCD that trips with its test button; the essential loads run with the house line cut off and locked out at the pillar.
- **Don't:** hang the fridge from a terminal of the panel under repair; run the extension cord through the panel door; feed the temporary circuit "from a neighbor's socket outlet".
- **Source:** Decreto 911/96 art. 86 (construction site installation treated as a permanent installation, with earthing and automatic disconnection; no bare conductors), per ELEC-SEG-14 and ELEC-SEG-15; AEA 90364-7-704 ed. 2026 (construction sites) or, where it has not yet been adopted, annex 771-B.7 of 771 (see ELEC-NOR-5); ELEC-SEG-28 and ELEC-SEG-34 (live incoming terminals; everything before the meter belongs to the utility). Use of the temporary panel for essential service and the branch at the pillar: site practice, **not verified in a primary source**; what each utility allows at the pillar: **not verified**.
### ELEC-EQU-10: Replace or repair
- **Rule:** repair when the fault is located in one element (a socket outlet, a luminaire, a terminal, an accessible splice) and the rest of the circuit tests good. Replace the section or the whole circuit when the insulation is low throughout, the cable is unsuitable for where it is, or it cannot be inspected.
- **Why:** patching a cable buried without conduit or with cracked insulation leaves the next fault scheduled; rewiring a whole circuit for one burnt socket outlet is wasted time. The repair has to restore the original characteristics (or better ones).
- **How:** always replace: single-core cable buried without conduit; cable whose insulation cracks when bent; any splice inside a conduit or buried; outdoor boxes without an adequate IP rating; cable with a smaller cross-section than the MCB (*térmica*) requires; devices without certification or with insufficient breaking capacity (ELEC-REV-17). Repair is fine for: a damaged socket outlet or switch, a loose terminal, a luminaire with a worn-out gasket (replacing it with one with the correct IP). When in doubt, the megohmmeter (megger) decides: if after repair the circuit does not come out in the range of the healthy ones, it gets replaced.
- **Verify:** after repair, the circuit tests like similar ones (tens or hundreds of MΩ), not "just above 1 MΩ".
- **Don't:** pull new cable through a conduit full of old cables without removing them; "splice it properly with tape" on a buried section; leave a splice in a box that will end up covered by the floor.
- **Source:** Decreto 911/96 art. 87 (the repair must ensure full restoration of the original characteristics); ELEC-CON-19, ELEC-CON-21 (underground runs, splices only in boxes); ELEC-DIA-17 (rewire completely if the insulation is low throughout).

### ELEC-EQU-11: Each circuit is closed out with measurement and records before moving on to the next
- **Rule:** a circuit is not considered finished until it has been tested (insulation, PE continuity, polarity and, energized, its RCD (*diferencial*) trip), recorded in the survey (*relevamiento*), labeled in the panel (distribution board, *tablero*) and verified by the person in charge. Only then does the assignee take another package.
- **Why:** with several people working, "we'll close everything at the end" turns into twenty untested circuits and nobody who remembers what each person touched. Closing one at a time always leaves part of the house ready to hand over.
- **How:** use this guide's "Circuit closing checklist". Statuses in the survey: the technician moves the circuit to `repaired` with `gateway electricidad plan status <F> <CIRCUIT> repaired --tech "Technician B"` and loads the measurements; the person in charge, after seeing the measurements and the test, moves it to `verified`.
- **Verify:** `plan summary` shows the circuit as `verified` with dated measurements; new label placed in the panel.
- **Don't:** energize a repaired circuit without testing insulation; mark as `verified` yourself what you repaired yourself (someone else verifies it, normally the person in charge).
- **Source:** Decreto 911/96 art. 79 c) IV (the insulation resistance test is a condition for restoring service); ELEC-MED-4, ELEC-MED-6, ELEC-MED-12. Verification by a second person: quality practice, **not verified in a primary source**.

### Team organization

### ELEC-EQU-12: One person responsible for the work per job, and a coordinator if there is more than one crew
- **Rule:** on each job there is **one** person responsible for the work (*responsable del trabajo*: work leader or person in charge of lockout), named, present on site while people are working: they decide what gets cut off, place the locks at the isolation points, supervise the verification, keep the records and are the only one who restores service. In this guide that person also fulfills the decree's role of person responsible for the task (*responsable de la tarea*). If two crews work (for example, 6 people in two groups of 3), each has its leader and one of them coordinates the whole.
- **Why:** Decreto 911/96 art. 79 splits the sequence between two roles: the "responsable del trabajo" (person responsible for the work) isolates, locks, labels and carries out the lockout at the supply points (subsec. a), and the "responsable de la tarea" (person responsible for the task) repeats the steps at the workplace, checks personally before restoring service and unlocks (subsec. b, c and d). The decree does not define them separately. On a small job, having the same person fill both roles is a criterion of this guide, not the letter of the decree: it avoids the person restoring service not being the one who knows what was cut off. If "anyone" cuts off and restores, nobody knows who is inside.
- **How:** the person in charge is the licensed professional or qualified installer who runs the job, or a trained person they designate in writing on the work permit. If they have to leave, they transfer the role formally (ELEC-EQU-19) or the job stops. With 2 people, one is in charge and also works; with 4 or more, it is better for the person in charge not to have their own package and to devote themselves to coordinating, measuring and verifying.
- **Verify:** the day's work permit says who the person in charge is and is signed; everyone knows it from the start-of-day talk.
- **Don't:** "whoever arrives first cuts off"; leave the job with people working and the person in charge away.
- **Source:** Decreto 911/96 art. 79 a) ("el responsable del trabajo deberá" (the person responsible for the work shall), at the supply points) and b), c) and d) ("el responsable de la tarea" (the person responsible for the task): repetition at the workplace, personal check, restoring service and unlocking), text reread 2026-11-15; outside construction, Decreto 351/79 Anexo VI item 1.2.3 (numbering inferred; role of a single "Responsable del Trabajo", per ELEC-SEG-9). Combining both roles in one person: criterion of this guide. OSHA 1910.147 (f)(3)(ii)(A) and (C) (person with primary responsibility for the group and a coordinator when there are several crews), as a reference.

### ELEC-EQU-13: Who can do what within the team
- **Rule:** each person does only what corresponds to their training and to what the person in charge assigned them: the helper without electrical training does not operate the panel, does not measure live and does not verify absence of voltage for others; live measurements (leakage clamp meter, RCD trip, voltage at terminals) are done by the person in charge or by someone they designate in writing who is trained, under the conditions of ELEC-EQU-32.
- **Why:** a mixed team (licensed electrician, journeyman, semi-skilled worker, helper) is normal. The typical accident is the helper who is sent "to switch off the MCB that says kitchen".
- **How:** in the start-of-day talk, say out loud who measures, who operates and who only works in their box with their padlock on. The helper also has their own padlock and tag if they are going to touch anything in the installation, and verifies absence of voltage at their point with an instrument if trained for it; if not, they work only on tasks without conductors (running conduit, pulling empty conduit, tidying up) or alongside the technician who verified.
- **Verify:** the work permit lists each person with their role.
- **Don't:** let the owner or a neighbor "help" at the panel; let a helper restore service.
- **Source:** Decreto 911/96 art. 76 and art. 86; outside construction, Decreto 351/79 Anexo VI item 1.2.2 (numbering inferred; training), per ELEC-SEG-9.

### ELEC-EQU-14: Progress board with statuses everyone understands
- **Rule:** progress is tracked per circuit with fixed statuses, in the survey, and is updated at the moment (not at night from memory): `not_surveyed` → `surveyed` → `measured` (insulation OK) or `fault` → `under_repair` → `repaired` → `verified`.
- **Why:** with several people, the circuit status is safety information: a circuit `under_repair` has someone inside; one at `fault` is not energized; only the `verified` ones are handed over.
- **How:**
  - The agent updates with `gateway electricidad plan status <F> <CIRCUIT> <STATUS> --tech "<name>" --note "<text>"` (atomic write with a `.bak` copy) when a technician tells it via Telegram ("C7 en reparación, Técnico B", "C7 under repair, Technician B").
  - `gateway electricidad plan summary <F>` gives the table by circuit, technician and status; `plan draw <F> --color status` gives the colored drawing to send to the group.
  - `plan validate` warns if there is a circuit `under_repair` with no assignee.
  - A printed copy of the drawing by status is stuck up near the panel; it is marked by hand and transferred to the file.
- **Verify:** at any moment, `plan summary` matches what the padlocks on the panel say: each circuit `under_repair` has its assignee's padlock.
- **Don't:** use made-up statuses ("casi" (almost), "anda" (works)); mark as `repaired` a circuit that was not tested.
- **Source:** site management practice; the tool's status contract in [surveys-and-drawings.md](surveys-and-drawings.md) (ELEC-PLA-20). **Not verified in a primary source** (no norm sets these statuses).

### ELEC-EQU-15: 5-minute talk at the start of each workday
- **Rule:** before opening the panel, the whole team meets with the person in charge for 5 to 10 minutes: plan for the day, what is energized, who does what, particular risks, emergencies. Nobody starts without the talk, and whoever arrives late gets it before starting.
- **Why:** in rehabilitation the state of the installation changes from one day to the next (what was cut off yesterday may be in service today). The talk is the moment when that gets said.
- **How:** fixed script:
  1. What stays energized today (drawing colored by status, temporary circuit included).
  2. The day's packages and assignees (sheets from `plan sheets`).
  3. Lockout points, group lockbox, who has which padlock.
  4. Back-feed sources on this job (ELEC-EQU-26).
  5. The day's risks: height, drilling, rain, occupants in the house, pool.
  6. Emergencies: emergency cut-off points according to what is live today (meter pillar, temporary circuit, sub-panel, generator set), who calls, exact address in writing, first-aid kit, ART (workers' compensation insurer) number (ELEC-EQU-30).
  7. PPE and instrument check (voltage tester proved working) per the daily checklist (ELEC-SEG-25).
  It is recorded on the work permit with each person's signature.
- **Verify:** the day's permit is signed by everyone present.
- **Don't:** do the talk over WhatsApp "because they already know"; skip it on the last day "because there's not much left".
- **Source:** Decreto 911/96 art. 76 (training of personnel in electrical risks); daily check: ELEC-SEG-25. The start-of-day talk as a format: safety practice, **not verified in a primary source** as a literal obligation.

### ELEC-EQU-16: Communication with closed phrases and confirmation
- **Rule:** every switching operation or application of voltage (energizing, insulation testing, testing an RCD) is announced to everyone and waits for each person's confirmation. Short, fixed phrases are used and whoever receives the order repeats it.
- **Why:** in a two-story house with a garden you cannot see your coworker; a shout from the panel does not reach the back. The misunderstanding "did you say C7 or C17?" costs dearly.
- **How:** two-way radio (*handy*) on large or noisy jobs; otherwise, cell phone in a group call or messages, with the person in charge as the only one who gives the order. Phrases: "Voy a megar C7, ¿alguien en C7?" (I'm going to megger C7, anyone on C7?) → each one answers "Fuera de C7, Técnico B" (clear of C7, Technician B). "Energizo grupo dormitorios en un minuto" (energizing bedrooms group in one minute) → "Fuera, Técnico C" (clear, Technician C). If someone does not answer, it is not done. Circuits are named by their survey ID, the same on the panel, the drawing and the sheet.
- **Verify:** the panel labels match the IDs on the drawing; everyone has their radio charged or their cell phone with signal.
- **Don't:** "I told the group" with a message nobody read; name circuits by what you think they feed ("la de la cocina", the kitchen one).
- **Source:** OSHA 1910.333(b)(2)(v)(D) (visual check that everyone is clear before re-energizing), as a reference. Communication with confirmation: safety practice, **not verified in a primary source** in Argentina.

### ELEC-EQU-17: Only the person in charge energizes, with all padlocks removed and people counted
- **Rule:** nobody other than the person responsible for the work restores voltage, and only when: each technician has removed their own padlock from the group lockbox, the person in charge has counted the people and walked the area, tools, leftover material, signs and earthing devices have been removed, the neutrals that were touched are reconnected and tightened, and the circuit's insulation test has been done. If others are still working in another part of the installation, ELEC-EQU-33 applies first.
- **Why:** this is the moment of greatest risk in group work: a person the person in charge did not see, still in a box in the garden. And a loose or wrongly reconnected neutral in three-phase leaves loads between phases, with up to 380 V (ELEC-EQU-34).
- **How:** (1) call by radio or voice to everyone (ELEC-EQU-16); (2) group lockbox empty of personal padlocks; (3) walk-through: covers on, or boxes that were worked on with no exposed conductors; (4) at the panel: each neutral in its own two-pole MCB or in its RCD's terminal block, tightened to the manufacturer's torque, main neutral firm, inner cover (dead front, *contratapa*) on (ELEC-EQU-34); (5) circuit measurements loaded; (6) announcement "energizo en un minuto" (energizing in one minute); (7) removal of their operations padlocks, closing in stages, from upstream to downstream, standing to one side (ELEC-MED-12, ELEC-SEG-29); (8) in three-phase, before connecting loads, L-N voltage on each phase: even, around 220 V; (9) test the RCD with its button and with a tester.
- **Verify:** no personal padlock remains in the lockbox; the list of people present matches the answers; L-N even on all three phases.
- **Don't:** "energize for a second to test" with people working on other circuits of the same group; energize a group because "the padlocks left belong to people who left" (ELEC-EQU-22).
- **Source:** Decreto 911/96 art. 79 c) I to IV and d) (the person responsible for the task personally checks that earths, tools, leftover material and signs have been removed, that the personnel have moved away and that the insulation test was done; then unlocks); ELEC-SEG-7; OSHA 1910.147 (f)(3)(ii)(D) and 1910.333(b)(2)(v), as a reference. Checking neutrals and L-N per phase: practice of this guide (ELEC-EQU-34), **not verified in a primary source**.

### ELEC-EQU-18: End of the workday: nothing half-done left energized
- **Rule:** at the end of the day, no circuit with incomplete work stays energized, no box is left open with conductors within reach and no panel is left without its inner cover. Whatever is incomplete stays cut off, locked out by the person in charge with a "FUERA DE SERVICIO - TRABAJO EN CURSO" (out of service - work in progress) tag, and recorded.
- **Why:** at night the house is occupied: kids, pets, the owner who "switches the MCB on to see if it works now". A half-finished installation is a trap for whoever was not on the job.
- **How:**
  1. Each technician leaves their package in a safe state: ends individually insulated with a terminal or connector (not tape alone), boxes covered, nothing hanging from the ceiling.
  2. Each technician removes their personal padlock **only** after the person in charge has placed or keeps the operations padlock on the incomplete package.
  3. The person in charge walks the house with the drawing, leaves the panel closed and updates statuses (`plan status`) and the site report.
  4. Explain to the owner what works and what doesn't, and that the panel is not to be touched (the enclosure locked with a key if possible).
- **Verify:** the day's `plan summary` matches the panel. The only things left energized are what is `verified`, what was never touched and is as it was (no lifted neutrals or changed connections) and the temporary circuit. A circuit at `measured` does not yet have its neutrals checked or its RCD tested: it stays open, locked out and tagged.
- **Don't:** leave "the MCB on, since the cable is insulated with tape anyway"; take away the operations padlock key without leaving a record.
- **Source:** Decreto 911/96 art. 86 (bare conductors); Decreto 351/79 Anexo VI item 3; ELEC-SEG-20. End of the workday with the person in charge's padlock: LOTO practice, **not verified in a primary source**.
### ELEC-EQU-19: Shift change and people coming in or leaving
- **Rule:** when the shift changes, or one person leaves and another replaces them on a work package, protection is never interrupted: the incoming person puts on their padlock **before** the outgoing person removes theirs, and they hand over the state of the package in person. If the person leaving is the person in charge (*responsable*), they transfer the role in writing on the permit.
- **Why:** between one person removing their padlock and the other putting theirs on, the circuit has no personal lock: that is the gap through which reconnection gets in.
- **How:** handover at the panel (*tablero*), both people together: (1) the incoming person checks that the device is still open and locked; (2) they put on their padlock and tag; (3) the outgoing person explains what they did, what is left, and what is loose; (4) the outgoing person removes their padlock; (5) the incoming person verifies absence of voltage at the work point themselves (ELEC-EQU-25); (6) `assigned_to` is updated in the survey (*relevamiento*).
- **Verify:** at no moment were there zero personal padlocks on a package with work in progress.
- **Don't:** leave the padlock on "for tomorrow's person to remove"; accept the package over the phone.
- **Source:** OSHA 1910.147 (f)(4) (specific procedures for shift or personnel changes, with an orderly transfer of protection between the person leaving and the person coming in), as a reference. **Not verified in a primary source** in Argentina.

### Safety specific to group work

### ELEC-EQU-20: Group lockout: operations padlocks, group lockbox and one personal padlock per person
- **Rule:** when one isolation protects several people, the person in charge locks each isolation point (the house panel cut-off for field work, per ELEC-EQU-24; the protection of the line to the house at the meter pillar (*pilar*) whenever someone works inside the panel, ELEC-EQU-31; outdoor sub-panel; back-feed sources) with operations padlocks and a tag, and leaves the keys inside a group lockbox. Each person who is going to work puts **their** personal padlock and **their** tag on the box (or on the lockout hasp if there is only one point) before starting, and removes it when they stop working.
- **Why:** with a single isolation point a lockout hasp is enough; with several points (main, outdoor sub-panel, generator set) the group lockbox makes sure nobody can recover the keys of the isolation points while even one personal padlock is still on.
- **How:**
  1. The person in charge isolates each source, fits a lockout device, operations padlock (a different color from the personal ones) and tag at each point, and verifies absence of voltage downstream.
  2. They put the keys of those padlocks in the group lockbox and close it with their own padlock.
  3. A list of the locked points is written on the work permit and on a tag on the box.
  4. Each technician: puts their padlock on the box, verifies absence of voltage at their own work point (ELEC-EQU-25), works; when finished, removes their padlock.
  5. With a single point (for example, the house panel cut-off): a lockout hasp on the lockout device, and each person hangs their padlock on the hasp.
  6. Full re-energizing: ELEC-EQU-17. Energizing one part while others keep working, or moving to per-circuit lockout: ELEC-EQU-33.
  Reference products: portable group lockboxes for a dozen padlocks that do not let the keys out until the last padlock is removed (for example, Master Lock 498A); lockout hasps with 4 to 6 holes; common brands Master Lock, Brady, ABUS, with local equivalents.
- **Verify:** as many personal padlocks on the box as people working; the keys of all points are inside; every tag is legible.
- **Don't:** use a single "team" padlock for everyone; leave the box open or the keys of the operations padlocks in someone's pocket.
- **Source:** Decreto 911/96 art. 79 a) II (locking of the isolating devices and the label "Prohibido Maniobrar" (do not operate) with the name of the person in charge); ELEC-SEG-4; OSHA 1910.147 (f)(3)(ii)(D) (each authorized worker puts a personal padlock on the device or group lockbox when starting and removes it when finishing), as a reference; Master Lock, 498A data sheet (consulted 2026-11-15: each worker puts a personal padlock on the box; the keys cannot be taken out until the last padlock is removed).

### ELEC-EQU-21: One padlock, one person, one key
- **Rule:** each technician has their own personal padlock, identified with their name (or an attached tag), with a single key that they carry on them. Lockout padlocks are used only for lockout: they are not lent, not shared and not used for the toolbox.
- **Why:** if two people have the key to the same padlock, either of them can remove it thinking the other one is done. A padlock with no visible owner does not say who is working.
- **How:** dielectric or plastic-body safety padlocks (a bicycle lock is not used), one color for personal padlocks and another for operations padlocks; a tag with name, company and how to reach the person. No key copies and no master keys: the only method for removing someone else's padlock is the one in ELEC-EQU-22 (cut by the person in charge, with a search, walkthrough, witness and record).
- **Verify:** at the start-of-day talk each person shows their padlock and their key.
- **Don't:** leave the key in the padlock; hang the key on the panel; use someone else's padlock "because I forgot mine".
- **Source:** OSHA 1910.147 (c)(5)(ii) (lockout devices individually identified, used only for energy control, standardized by color, shape or size, durable, and showing the identity of the person who applied them), as a reference; ELEC-SEG-4. A single key with no copies: LOTO practice, **not verified in a primary source** in Argentina.

### ELEC-EQU-22: If someone left with the key: formal procedure, never "I'll take it off"
- **Rule:** a person's padlock is removed only by that person. If they are not there and their padlock is still on, a written procedure is applied, decided and carried out by the person in charge, with a witness and a record; a coworker never cuts it on their own.
- **Why:** "they must have left" is exactly what people think before energizing on top of someone who was at the back of the garden or in the attic.
- **How:**
  1. Call the person and search for them across the whole site, including roof, attic, basement, garden and vehicle.
  2. If they answer: it is preferable that they come back and remove their padlock themselves. If they cannot come back, they confirm by phone that they left the site and where they left their work, and steps 3 to 5 are still followed and their confirmation is recorded (time, who spoke to them).
  3. If they do not turn up: the person in charge and a witness walk through the absent person's whole package with the drawing, verify that nobody is there and that the work was left in a safe state (boxes, loose wire ends, tools).
  4. The person in charge cuts the padlock (the device is not forced) and records on the permit: who, when, why, who was the witness, what was found.
  5. Before their next entry to the site, the absent person is told that their padlock was removed and is given a new padlock.
  6. Why it happened is analyzed at the next talk.
- **Verify:** the permit has the record signed by the person in charge and the witness.
- **Don't:** cut the padlock "so as not to lose the day"; open the group lockbox with a pry bar; energize with someone else's padlock still on.
- **Source:** OSHA 1910.147 (e)(3) (the device is removed by whoever applied it; if they are not there, it may be removed under the direction of the employer with a documented procedure that includes verifying that they are not at the facility, making all reasonable efforts to contact them and making sure they know before they return to work), as a reference; ELEC-SEG-7 ("si no aparece, decide el responsable con un procedimiento escrito" (if they do not turn up, the person in charge decides with a written procedure)).

### ELEC-EQU-23: DIN MCBs (*térmicas*): lockout device for PIA, and what to do if it does not fit
- **Rule:** the device that is opened is physically locked with a lockout device for DIN rail breakers and a padlock. Before the job, test that the lockout device fits the MCBs (*térmicas*) in that panel; if there is no lockout device that works, lock a device upstream that can be locked, or the whole enclosure with a latch and padlock.
- **Why:** PIA levers change shape and size by brand and product line, and a patched-together panel has several kinds. A tag stuck on with tape does not stop anyone from pushing the lever up.
- **How:** PIA lockout devices that fit into the holes of the lever or clamp around it ("pin-in" and "pin-out" types, or universal ones with a screw); for example, the Master Lock S2391 is for pin-out DIN rail PIA, with a lever opening of 11 to 13 mm according to the data sheet; for pin-in levers or levers of other sizes there are other models or universal lockout devices with a screw. For 2- or 4-pole breakers with tied levers, the lockout device goes on the common lever. If the enclosure has a door with padlock tabs, add the lockout hasp on the door. Bring more than one model to the job.
- **Verify:** with the lockout device and padlock on, the lever does not go up even when forced by hand.
- **Don't:** lock with a cable tie, tape or a stick; remove the lever from the device; leave only the tag on a device that can be locked.
- **Source:** Decreto 911/96 art. 79 a) II; OSHA 1910.333(b)(2)(iii)(D) (a tag without a padlock requires an additional equivalent safety measure), as a reference; Master Lock, S2391 data sheet (consulted 2026-11-15). Compatibility with Argentine brands: **not verified**; test it on each panel.

### ELEC-EQU-24: If the MCB (*térmica*) does not break the neutral or there is a shared neutral, lock the panel cut-off
- **Rule:** in field work (cables, boxes, outlet points (*bocas*)), work with only the circuit's MCB locked only if that MCB breaks phase and neutral (two-pole in single-phase; all poles in three-phase) and the circuit's neutrals have been checked by the two methods in ELEC-EQU-5. Otherwise, lock the panel cut-off: the house main breaker if it has been checked that it cuts everything in the panel, including the RCD (*disyuntor* / *diferencial*, ID) (in the photo example it is not known whether the ID is before or after the main breaker: ELEC-REV-27); if not, the protection of the line to the house at the pillar. A panel **with no main MCB**, with an incoming ID and the MCBs below it, is treated the same way: as long as it has not been checked that this ID breaks all poles of the whole panel and is suitable for isolation, the isolation point is the one at the pillar. Once the panel is sectioned, the group's two-pole or four-pole ID is enough if it has been checked that the circuit's neutral comes only from it. For work inside the panel, ELEC-EQU-31 always applies.
- **Why:** an old panel has single-pole MCBs that leave the neutral connected, and neutrals that pass between circuits in junction boxes. With the MCB open, that neutral can carry current and have voltage to earth.
- **How:** in the diagnosis phase, the whole team works under the lockout of the panel cut-off (with the temporary panel supplying essential service, ELEC-EQU-9). Only once the panel is sectioned and the neutrals checked by (a) and (b) of ELEC-EQU-5 do you move to per-circuit or per-group lockout, with the transition in ELEC-EQU-33. At the box you work on, also check for voltage on the circuit's own neutral and on other circuits' neutrals that pass through, as Decreto 911/96 art. 79 b) requires at the work location (ELEC-EQU-25).
- **Verify:** the circuit's sheet says what is locked, and if it says to lock out the main switch too (the panel cut-off) it is because the neutrals still have to be checked or there are `doubtful` outlet points.
- **Don't:** trust a single-pole MCB; assume the neutral "has no voltage"; switch off the house main breaker without knowing whether it leaves the ID upstream live.
- **Source:** ELEC-TAB-16 and ELEC-PRO-1 (MCB that breaks all poles; AEA 770.16.5.1); Decreto 911/96 art. 79 b) (verify absence of voltage on the neutral too at the work location); ELEC-REV-27 (the main breaker does not cut what is before it); ELEC-PLA-15; ELEC-SEG example case, step 5 (shared neutral in old buildings).

### ELEC-EQU-25: Each person verifies absence of voltage at their own work point
- **Rule:** the fact that the person in charge verified at the panel does not exempt anyone: before touching, each technician verifies absence of voltage at the box or point where they are going to work, with a two-pole voltage tester (*detector bipolar*) proved before and after on a known source, between all conductors (L-N, L-PE, N-PE and between phases), including the conductors of other circuits that pass through that box.
- **Why:** the lockout guarantees that nobody closes that device; it does not guarantee that the cable in that box comes from that device. In a patched-together installation that is exactly what is in doubt.
- **How:** procedure in ELEC-SEG-5. Known source: the temporary panel (it is live on purpose) or a voltage proving unit. One tester per person or, at minimum, per pair; never "pass it to me when you're done". If voltage appears where it should not: everyone out, tell the person in charge, correct the map before continuing. Two traps typical of an old installation:
  - **Light switch that breaks the neutral:** with the switch off, the lampholder or the luminaire's terminal block (*bornera*) is left with phase. Never work on an outlet point trusting the light switch or that "the light is off": lock the MCB (or the panel cut-off) and verify L-PE at the lampholder or terminal block. A switch that breaks the neutral is marked as a fault and corrected (ELEC-MED-7).
  - **MCB with welded contacts:** after several short-circuit trips, the contacts of a PIA can stay stuck: the lever down does not guarantee an open circuit. It is another reason to verify at the point and not at the lever; a PIA that left voltage with the lever down is replaced.
- **Verify:** each technician can say at which point they measured, with what, and that they proved the instrument before and after; this is noted on the permit ("Verificó en su punto" (verified at their point) column).
- **Don't:** use a non-contact voltage tester (*buscapolo*); measure only at the panel; measure only the phase of your own circuit and not the neutral or the other circuits' conductors in the box.
- **Source:** Decreto 911/96 art. 79 b) (at the work location, the person responsible for the task repeats the isolation steps and verifies absence of voltage on the neutral too) and art. 78 b); ELEC-MED-7 (the switch breaks the phase). Welded contacts: maintenance experience, **not verified in a primary source**; ELEC-SEG-5 (SRT Manual TST 2023: prove the tester before and after; IEC 61243-3); OSHA 1910.147 (d)(6) (verify isolation before starting), as a reference. Note: OSHA 1910.333(b)(2)(iv)(B) requires proving the instrument before and after only above 600 V; this guide requires it always.

### ELEC-EQU-26: Sources that can come back: a list per job and lockout of each one
- **Rule:** before the first day, the person in charge makes a list of all sources that can energize what is going to be touched, and each one is isolated and locked in the group lockout: generator set (and its transfer switch), UPS, inverter and solar panels with batteries, another panel or another phase that supplies loads in the same area, the temporary panel, motor capacitors (pool pump, gate, compressors).
- **Why:** large, patched-together houses often have more than one supply: the gate supplied from the pillar, the pool pump with its own panel, a two-way switch that mixes two circuits, a generator connected "with a male-to-male plug". Each one is a back-feed that the panel cut-off does not stop.
- **How:**
  - Generator set: it must be connected through a transfer switch; lock the transfer switch in "red" (mains) or "apagado" (off) and disconnect the automatic start (ELEC-SEG-21, ELEC-ESP-25). If you find a generator connected without a transfer switch, it is a shock hazard: disconnect it and report it.
  - UPS: it keeps supplying voltage with the mains cut; switch it off, disconnect the battery if it is part of the fixed installation, and label it (ELEC-ESP-27).
  - Solar panels: the DC side does not switch off during the day; the inverter is isolated on the AC side and on the DC side according to the manufacturer (ELEC-ESP-22, ELEC-ESP-23, ELEC-ESP-24).
  - Another panel or another phase: in three-phase, a box can have conductors from two phases and from two panels; verify at each box (ELEC-EQU-25).
  - Motor capacitors: discharge them before touching the motor terminals, with the manufacturer's time or procedure.
  - In an area with a real possibility of back-feed (on-site generation), earthing and short-circuiting at the work point (ELEC-SEG-6).
- **Verify:** the list of sources is on the work permit and each one has its operations padlock with its key in the group lockbox.
- **Don't:** accept "there is no generator" because the owner did not remember (look for: thick cables from the garage, industrial plugs, transfer switches); trust that the UPS "switches off by itself".
- **Source:** Decreto 351/79 Anexo VI 1.1.4 d) (earthing at all points through which voltage could arrive) and Decreto 911/96 art. 79 a) I (separate from any possible supply), per ELEC-SEG-6; ELEC-ESP-22 to 27.
### ELEC-EQU-27: The megohmmeter is also a voltage source: announce it and coordinate
- **Rule:** before an insulation test, the person testing confirms that nobody is touching that circuit or any conductor that shares boxes with it, announces it by two-way radio (*handy*) or voice, waits for everyone's confirmation and, when finished, lets the instrument discharge the circuit before anyone touches it again.
- **Why:** the megohmmeter (megger, *megóhmetro*) applies 500 V DC to the isolated circuit. With a single person that is controllable; with six, the coworker who is stripping a cable in a box on that circuit gets the discharge, even though the panel is locked.
- **How:** insulation testing (*megar*) is a scheduled task, not something done "while you're at it": the person in charge sets a window ("de 10 a 11 se mega el grupo dormitorios; nadie trabaja en dormitorios" (from ten to eleven the bedroom group is megged; nobody works in the bedrooms)); the circuit is used as the work package: if it has an assignee, that assignee is the only one who can request or do the test. The loose ends of the circuit under test are identified and kept apart.
- **Verify:** before each test there was an announcement and confirmation; in the survey the test is recorded with the date and who did it.
- **Don't:** test the whole panel from the main breaker with people working in boxes; touch the loose ends before the instrument shows the discharge.
- **Source:** ELEC-MED-4 and ELEC-DIA-4 (announce that the megohmmeter applies 500 V DC; don't touch until discharged). Group coordination: practice of this guide, **not verified in a primary source**.

### ELEC-EQU-28: Signage, barriers and an occupied house
- **Rule:** put signs on the panel (*tablero*) ("PELIGRO - PERSONAS TRABAJANDO - NO MANIOBRAR" (danger, people working, do not operate)), on each open box and each work area, and tape off what nobody from outside should step on (open trench, ladder, temporary cables). If the house is occupied, agree with the occupants which areas are not used and who their contact on the job is.
- **Why:** in a rehabilitation the house is still alive: children, pets, the cleaner, the gardener with the string trimmer over the temporary cable, someone getting into the pool while work is being done on its pump.
- **How:** signs and tape at each work front; open trench covered or fenced off at the end of the day; pool out of use while its circuit or its equipotential bonding is being worked on; the temporary panel out of children's reach; a single point of contact with the owner (the person in charge), who is the only one who tells them what they can use.
- **Verify:** start and end walkthrough: all work fronts signposted; occupants informed.
- **Don't:** leave the trench open with cables overnight; accept that the owner "comes by to have a look" at the open panel.
- **Source:** Decreto 351/79 Anexo VI 1.1.4 e) and Decreto 911/96 art. 79 a) IV (signage and barriers around the work area); ELEC-SEG-20.

### ELEC-EQU-29: Height, ladders, drilling, dust and water near the panel
- **Rule:** first isolate and lock, then climb or drill. Non-metallic ladders in good condition; a cable detector before drilling or chasing, knowing that it does not detect everything; and the panel protected from the site's dust and water.
- **Why:** in a rehabilitation you chase walls to run new conduits, drill for boxes and work a lot on ceiling outlet points (*bocas*) and eaves; with several people, one chases the wall where another has a circuit still in service.
- **How:**
  - Height: ELEC-SEG-18 (fiberglass ladder, secured, one person holds the ladder if needed; harness from 2.50 m; Res. SRT 61/2023).
  - Drilling or chasing: with the drawing, the cable detector and the area's circuits locked (ELEC-SEG-19). The person chasing tells the person in charge which area they are going to chase; if there is a circuit in service in that wall, it is isolated.
  - Dust and water: cover the panel with plastic while chasing or sanding nearby (without covering the ventilation of a panel energized for hours); no pressure washer or hose near the panel or open outdoor boxes; vacuum instead of blowing.
  - Rain: no outdoor work in rain or with flooded ground; open outdoor boxes are covered.
- **Verify:** ladders checked in the daily check; before each drilling, area locked.
- **Don't:** stand on a chair; drill "by eye" straight above or below a switch; wet the floor around the panel to keep the dust down.
- **Source:** Decreto 911/96 arts. 52, 54, 57, 112 (fall arrest from 2.50 m), 214-220 (ladders) and 221-227 (scaffolding), and Res. SRT 61/2023, per ELEC-SEG-18; Decreto 911/96 art. 78 c) (do not use metal ladders); Res. SRT 503/14 only for trenches and excavations (buried installations), per ELEC-SEG-19. Drilling or chasing walls with a detector and the area isolated is site practice, **not verified** as regulatory text.

### ELEC-EQU-30: Emergencies: roles defined beforehand, ART and record afterwards
- **Rule:** before starting, at the talk, the following are defined: the emergency isolation points according to what is live that day (meter pillar (*pilar*), temporary supply branch, house panel, outdoor sub-panel, generator set) and who isolates each one, who calls emergency services and the ART (workers' compensation insurer), who meets the ambulance at the door, and where the first aid kit is. Every accident is reported to the ART and recorded.
- **Why:** with several people, everyone assumes someone else called. In a large house, the ambulance loses minutes looking for the entrance. And this job has several sources: the house main isolation does not cut the temporary supply or its branch at the pillar, which is exactly what is most likely to be live near people.
- **How:**
  - Person who received a shock: isolate at the point that supplies what they are touching, don't touch them while live, call, CPR (ELEC-SEG-23). Numbers according to the jurisdiction (107, 911, 100) and the ART's number, written on the work permit and on the panel door; exact address with cross streets.
  - The emergency isolation points are marked on the day's drawing (`plan draw`, with the temporary supply and the sub-panel) and on the permit.
  - At least one person per shift trained in CPR; first aid kit and, if there is one, location of the nearest AED (*DEA*).
  - Afterwards: report to the ART and the SRT by the employer, entry in the accident register, scene left untouched until investigated, installation locked (ELEC-SEG-24).
  - Independent technicians or self-employed workers under the *monotributo* regime with no employees: they have no ART, because Ley 24.557 makes coverage mandatory for employees on payroll (*en relación de dependencia*) and covers self-employed workers only if the Executive Branch includes them. Whoever hires them (company or private individual) asks them before the first day for proof of valid personal accident insurance that covers the task, and notes it on the permit. If there are several companies on site, safety coordination between the main contractor and subcontractors is set up by the health and safety officer (Res. SRT 35/98).
- **Verify:** the day's permit lists the emergency isolation points, the roles and the numbers, and each person's coverage (ART or insurance).
- **Don't:** "I'll take them in my car" without calling; not report because "it was minor"; let someone work without knowing what covers them.
- **Source:** Ley 24.557 art. 2 ap. 2 b) (self-employed only if the Executive Branch includes them), art. 31 inc. 2 c) (the employer reports accidents to the ART and the SRT) and e) (accident register per workplace), art. 31 inc. 3 e) (the worker reports to the employer) and art. 43 (benefits start with the report), updated text consulted 2026-11-15; Decreto 911/96 art. 76 (training in first aid for accident victims); Res. SRT 35/98 (coordinated safety program between contractors, per site-safety.md); ELEC-SEG-17, ELEC-SEG-23 and 24. Requiring personal accident insurance from independent workers: recommendation of this guide (matches ELEC-SEG-17), not a regulation. Current SRT reporting procedure (forms, deadlines): **not verified in a primary source**.

### Work inside the panel, transitions and working-day conditions

### ELEC-EQU-31: Field work and work inside the panel are isolated at different places
- **Rule:** two cases are kept apart. (a) **Field work** (boxes, outlet points, cables, luminaires): locking the device that supplies that section is enough, per ELEC-EQU-24. (b) **Work inside the panel** (lifting or reconnecting neutrals, disconnecting, replacing devices, fitting the inner cover (dead front, *contratapa*), dismantling, connecting the line of the outdoor sub-panel or of the temporary supply): isolate and lock **upstream of the panel**, at the protection of the line that comes into the house (at the pillar), and verify absence of voltage at the incoming terminals of the house main breaker and RCD (*disyuntor* / *diferencial*, ID) and on the incoming line. If the incoming supply cannot be isolated (there is no protection between the meter and the panel), cover the incoming terminals with an insulating shield or cap, work as in proximity with PPE and clearances (ELEC-EQU-32, ELEC-SEG-8), or ask the utility (*distribuidora*) for a disconnection.
- **Why:** with only the house main breaker locked, its incoming terminals are still live, as is the incoming line and, if the ID is before the main breaker, the whole ID with its terminals (in the case photo the order cannot be seen: ELEC-REV-27). It is work with your hand in the enclosure next to 380 V between phases. And a locked MCB (*térmica*) protects the field cable, not the inside of the panel: busbar combs (*peines*), incoming terminals of the other MCBs and the neutral terminal block are still live.
- **How:**
  1. Before the job, identify what protects the line to the house. If the pillar has a single breaker that would also have to supply the temporary supply, set up the branch in ELEC-EQU-9 so that the house has its own isolation point.
  2. Work inside the panel is not part of any package: the person in charge schedules it in windows ("de 8 a 10, tablero cortado desde el pilar" (from eight to ten, panel cut off from the pillar)) and does it themselves or through a technician they designate, with a second person present (ELEC-EQU-35).
  3. On the permit, the point "Tablero principal (pilar)" (main panel, pillar) is mandatory every time someone works inside the house panel.
  4. At the end of the window: inner cover fitted, neutrals reconnected (ELEC-EQU-34) and energizing with ELEC-EQU-17 or ELEC-EQU-33.
- **Verify:** before putting your hand in, two-pole voltage tester on the incoming terminals of the main breaker and the ID (between phases, L-N, L-PE and N-PE): no voltage, or covered if they could not be isolated.
- **Don't:** work on the neutral terminal block or a busbar comb with the panel energized "because my MCB is locked"; "I'm only loosening a neutral for a second"; switch off the main breaker and treat the enclosure as dead.
- **Source:** Decreto 911/96 art. 79 a) I and III (open the isolating devices closest to the work area and separate from every possible voltage source, verify absence of voltage) and art. 75 (clearances to uninsulated live parts); ELEC-SEG-8, ELEC-SEG-28 (what stays live inside the panel even if you switch off the main breaker), ELEC-REV-27. Field / panel separation as an organizational rule: criterion of this guide.

### ELEC-EQU-32: Measurements and switching with the installation energized: under what conditions
- **Rule:** switching from the front and live measurements (leakage clamp meter, RCD (ID) trip with a tester, voltage between phases and L-N, circuit identification) are done only by trained personnel authorized in writing by the person in charge, with a second person present who knows where to isolate, with class 0 insulating gloves tested by inflation, face protection, clothing without synthetic parts, an instrument rated CAT III at minimum (CAT IV at the pillar or the meter) with shrouded probes, and never on a panel without an inner cover or with live terminals within hand's reach. This guide treats them as measurements with their own limits, not as "live work" under the regulation of Res. SRT 3068/2014, which this crew does not do.
- **Why:** to clamp the phase and neutral of a circuit you have to put your hand into an enclosure with live bars and terminals; the panel in this case has no inner cover. An instrument without a category rating can explode on a transient, and switching onto a fault can cause an arc (ELEC-SEG-29).
- **How:**
  - Leakage clamp meter: preferably where the circuit comes out accessible with the inner cover fitted, or at the load with an adapter or extension with separable conductors (phase and neutral accessible in an insulated section). If there is no way to do it without bringing your hand near live parts, don't measure that way: use the megohmmeter with the circuit dead.
  - ID trip: with a plug-in tester in a socket outlet of the group, not with probes on the terminals.
  - Voltage at terminals: with the inner cover on, capped probes, standing to the side and the other hand out of the enclosure.
  - Insulating shields or caps over the terminals that cannot be isolated (ELEC-SEG-28).
  - In the 2-person variant, the other person is not at the back of the garden while live measurements are being made (ELEC-EQU-35).
- **Verify:** the permit lists who is authorized to make live measurements; gloves inflated that day; instrument with its category marked.
- **Don't:** measure with a clamp inside a panel without an inner cover; let the helper measure; use a tester without a category rating; rest your other hand on the enclosure.
- **Source:** ELEC-SEG-2 (live work is a separate trade, Res. SRT 3068/2014), ELEC-SEG-8, ELEC-SEG-10 (class 00/0 gloves with inflation test), ELEC-SEG-11, ELEC-SEG-13 (CAT III / CAT IV, IEC 61010-1), ELEC-SEG-28, ELEC-SEG-29, ELEC-SEG-32; Decreto 911/96 arts. 75 and 76. Classifying these measurements as outside the live-work regulation: criterion of this guide, **not verified in a primary source** (if the site's health and safety officer classifies them differently, their criterion prevails).

### ELEC-EQU-33: Energizing one part while others keep working: transition to per-circuit lockout
- **Rule:** before lifting a lockout that protects several people (the house main breaker or the pillar) to energize one part, each package still in progress gets its own lockout and nobody has their hands on conductors during energizing. After energizing, each assignee verifies again at their own point before touching.
- **Why:** when the padlock comes off the main breaker, the protection of all packages that depended on it is lost. ELEC-EQU-17 covers full re-energizing; here people are still inside, and if the map was wrong, voltage appears in a box that was thought to be dead.
- **How:**
  1. Any window of work inside the panel is closed first (ELEC-EQU-31): inner cover fitted, neutrals reconnected (ELEC-EQU-34).
  2. Each package still in progress: its MCB (two-pole or all poles) open, lockout device, the person in charge's operations padlock and the assignee's personal padlock. Only circuits with checked neutrals (ELEC-EQU-24); the others stay under an isolation that is not lifted.
  3. Call to everyone: hands off, boxes closed or loose ends insulated, confirmation from each person (ELEC-EQU-16).
  4. The padlocks are removed from the group lockbox of the point being lifted, and the person in charge energizes in stages what is `verified` or what is going to be tested (ELEC-EQU-17, steps 4 to 9).
  5. Each assignee of a package that stays locked verifies absence of voltage at their point (ELEC-EQU-25) before touching again. If voltage appears: everyone out, lock upstream again and correct the map.
  6. Record on the permit: which individual lockouts were fitted before lifting the group lockout and who verified afterwards.
- **Verify:** at no moment was a package with work in progress left without its own padlock; each assignee signed their verification afterwards.
- **Don't:** lift the padlock on the main breaker "for a moment" to test a circuit with people working on others; accept an MCB as good because "with the main breaker locked there was no voltage" (that proves nothing about the MCB).
- **Source:** OSHA 1910.147 (f)(3) (group lockout) and (f)(4) (orderly transfer of protection), as a reference; Decreto 911/96 art. 79 b) (verification at the work location). Transition sequence: criterion of this guide, **not verified in a primary source**.
### ELEC-EQU-34: Lifted neutrals: label them when you take them off, put them back in their place and tighten
- **Rule:** each neutral that is lifted is labeled on the spot with the circuit's ID and its loose end is insulated individually. Before energizing, each neutral goes back to its own two-pole MCB (*térmica*) or to the terminal block (*bornera*) of its RCD (*disyuntor* / *diferencial*, ID), tightened to the manufacturer's torque, and the main neutral is firm. In three-phase, after energizing and before connecting loads, measure L-N on each phase.
- **Why:** a neutral reconnected to another circuit's terminal recreates the cross-connection you wanted to eliminate. In three-phase, a loose or broken common neutral (*corte de neutro*) leaves loads on different phases in series between phases: they get up to 380 V, equipment burns out and there can be a fire (ELEC-EDI-11).
- **How:** photo of the panel (*tablero*) before touching; labels or numbered rings with the survey ID; a list of lifted neutrals in the circuit's `notes`; when reconnecting, one cable per terminal, ferrule on flexible conductors and the manufacturer's torque (ELEC-TAB-14); a gentle check pull; the person in charge checks the list against the panel before energizing.
- **Verify:** no neutral without a label or without a terminal; L-N even on all three phases, around 220 V; checklist item "Neutro reconectado y ajustado" (neutral reconnected and tightened).
- **Don't:** leave "temporary" neutrals in any old terminal; group several neutrals in one terminal to "finish today"; energize without checking the list.
- **Source:** ELEC-TAB-14, ELEC-TAB-15, ELEC-TAB-16; ELEC-EDI-11 (overvoltage from a broken neutral). Labeling and checking lifted neutrals: practice of this guide, **not verified in a primary source**.

### ELEC-EQU-35: Nobody works alone on the highest-risk tasks
- **Rule:** nobody works alone on: switching and work inside the panel, live measurements, tests with energizing (ELEC-EQU-5 b), attic, height and confined spaces. There is a second person in sight or within earshot, who knows where to isolate the day's points and how to call for help.
- **Why:** someone who gets stuck to live parts cannot let go or call for help. With 2 people the risk is concrete: R makes live measurements at the panel while T is at the back of the garden.
- **How:** with 2 people, the tasks on the list are done together; the one who is far away works only on their own locked package and keeps in contact by two-way radio (*handy*) or cell phone at fixed intervals; in the attic, the other person stays below. With more people, the person in charge assigns the companion at the talk.
- **Verify:** for every task on the list there is a named companion who knows how to isolate.
- **Don't:** stay behind alone to "finish the panel"; make live measurements while your coworker is out of earshot.
- **Source:** ELEC-SEG-32 (Decreto 911/96 art. 57; Res. SRT 61/2023 Anexo I punto 72). As a general rule for electrical tasks: criterion of this guide, **not verified in a primary source**.

### ELEC-EQU-36: Heat, fatigue and hurry are risks too
- **Rule:** long working days (sectioning, measurements) are planned with slack: a fixed time after which no task inside the panel that cannot be finished is started, breaks and water, and a planned safe stopping point for each day. If the day runs long, the end-of-day procedure applies (ELEC-EQU-18) and you don't "energize to test".
- **Why:** the pressure to get the power back on the same day, the heat of the attic or of a panel in the sun, and afternoon fatigue are what lead people to skip verification or to reconnect a neutral from memory.
- **How:** essential service runs on the temporary panel (ELEC-EQU-9), so there is no real hurry; in summer, the attic and the roof in short shifts and early; the person in charge watches their people and stops the task if someone is exhausted; explain to the owner from the first day that the house may be left with some circuits out until the next day.
- **Verify:** the day's plan has a stop time and a planned safe state for the night.
- **Don't:** start dismantling the panel in mid-afternoon; promise the owner "hoy te queda todo andando" (everything will be working today).
- **Source:** criterion of this guide, **not verified in a primary source** (no Argentine regulation setting breaks or heat limits for this task was read).

## Case: the house with the panel that grew by patches

### What is known (reading the photo)
Reference photo: a house panel with the door open (example file `photo_2026-11-15_04-35-27.jpg`,
not published). The detailed reading device by device, with what was seen, what was deduced and what is illegible, is in
[reviewing-a-panel.md](reviewing-a-panel.md) (worked example). For this guide, what matters is:

- **Seen:** a single 4-pole RCD, 63 A, 30 mA, next to a 4-pole C40 main MCB; one more 4-pole MCB (label partly illegible) and 26 two-pole MCBs C10 (lighting) and C15 (socket outlets), in four rows. Daisy-chained cable jumpers, no busbar comb (*peine*); no inner cover (dead front, *contratapa*); plain green cables; a loose cut cable.
- **Seen:** almost all devices are the same brand and product line; in rows 3 and 4 there are some with a different front or model (3.2, 3.7, 3.8; also 2.5 in the row above), stuck-on papers and two without a label. All labels are handwritten ("ILUM S. MUS.", "L. EXT CONTR", "PORTON", "PILETA"). Several levers in OFF (laundry, music room, garage, outdoor lights, the two without a label).
- **Told by the owner (data from the inquiry):** the MCBs at the bottom were added because of leakage and short circuits; the RCD trips.
- **Deduced:** given the owner's information, the bottom rows were added later; three-phase supply; all circuits depend on the same 30 mA ID (lack of selectivity (discrimination) and accumulated leakage, ELEC-EQU-3); the outdoor circuits, the pool and the gate are the first suspects (ELEC-EQU-4); high probability of crossed neutrals because of the additions (ELEC-EQU-5). The ID is in position 1 and the main MCB in position 2 (seen), but the actual ID / main connection order cannot be seen in the photo: until it is checked, the house main MCB is not taken as the isolation for the whole panel (ELEC-EQU-24, ELEC-EQU-31).
- **Not known:** whether there is a generator set, UPS or panels; cable cross-sections; condition of the earthing; whether drawings exist.

### Plan by working day for 3 people
Team: **R** = person responsible for the work (professional or qualified installer; coordinates, measures, verifies and is the only one
who energizes); **T1** and **T2** = technicians. The working days are indicative: the actual number is decided by the
measurements. Whatever is redone is designed and signed by whoever is required in the jurisdiction
([regulations-and-permits.md](regulations-and-permits.md)).

| Working day | What is done | Who | What stays energized | Statuses in the survey |
|---|---|---|---|---|
| 0 (prior visit, half day) | Photos, interview, look for back-feed sources, essential service, ask for drawings. See what protects the line to the house at the meter pillar (*pilar*) and whether it allows the temporary supply branch (ELEC-EQU-9); measure the current enclosure and decide whether the new one fits or building work is needed. The agent builds `survey.json` from the photo (`plan new`). Material order for the first days: DIN lockout devices that fit these MCBs, group lockbox, padlocks, insulating shields, inner cover, temporary panel and pillar branch; the new panel is quoted with margin (more IDs than seem necessary) and confirmed on day 2 | R | Everything as it is | Circuits `not_surveyed` |
| 1 (survey and map) | First hour, nobody else working: R isolates and locks at the pillar, covers the incoming terminals (ELEC-EQU-31, ELEC-EQU-32), sets up the pillar branch (line to the house + temporary supply) and installs the temporary supply for the fridge and the water pump (ELEC-EQU-9); fits the inner cover on the house panel with that isolation. The MCBs that were off stay off, with a "FUERA DE SERVICIO" (out of service) tag (ELEC-EQU-1). Rest of the day: identifying circuits one by one from the front (R switches standing to the side; T1 and T2 go round with a tester and a sketch per floor, ELEC-PLA-11 and 13); outlet points (*bocas*) that go dead with two MCBs, `doubtful`. The agent fills in rooms, points, routes; `plan validate`, `plan draw`, `plan single-line`. At the end of the day: circuits with obvious risk (bare cables, destroyed outdoor boxes) are left open and locked | R, T1, T2 | What was in service, with the inner cover; the dangerous circuits and the ones that were off, isolated; temporary supply and pillar branch | `surveyed` |
| 2 (measurements, in sequence) | The whole house panel under group lockout at the pillar, because there is work inside the panel (ELEC-EQU-31). (1) R, alone at the panel, lifts, labels and insulates all neutrals (ELEC-EQU-34). (2) T2 disconnects electronic loads and motors on a group of circuits following the sheets and announces "grupo X libre" (group X clear). (3) Measurement window: nobody touches that group or the terminal block; T1 does the insulation test with announcement and confirmation and waits for the discharge (ELEC-EQU-27). (4) Next group. Then, in its own window, R tests the neutrals against the set (ELEC-EQU-5 a) and checks the earthing. While a group is being tested, nobody works on that group's conductors or on the terminal block. The split of IDs is decided, and whether there will be an outdoor sub-panel | R, T1, T2 | Only the temporary supply | `measured` or `fault` per circuit |
| 2b (half day) | Purchase of the confirmed material; T2 assembles the new panel on the bench (4P main, ID per group, busbar combs, neutral terminal blocks per ID). R and T1 do the phase-neutral cross-connection test one circuit at a time (ELEC-EQU-5 b) on the `measured` circuits, with everyone out of the installation | R, T1, T2 | Only the temporary supply, except the circuit under test | `doubtful` resolved or noted |
| 3 and 3b (sectioning, 1.5 to 2 working days) | With the pillar isolated and locked: R and T1 dismantle the old panel, labeling each cable, and mount the new enclosure assembled on the bench. ID per group (bedrooms; living area and kitchen, type A; utility; outdoors; pool; gate and pump), green-yellow PE. Only `measured` circuits with checked neutrals are reconnected; the `fault` ones are left with insulated ends and their PIA open with R's operations padlock and a "FUERA DE SERVICIO" tag. Safe stopping point halfway: if it is not finished at the end of day 3, everything is left dead except the temporary supply and nothing half-connected (ELEC-EQU-18, ELEC-EQU-36). Commissioning in stages with ELEC-EQU-17 and ELEC-EQU-33 (ELEC-MED-12), L-N per phase, test of each ID with a tester | R, T1, T2 | At the end: the healthy indoor circuits under their new IDs; the temporary supply can be removed if the fridge is already on a `verified` circuit | `measured` move to `verified` after the test; `fault` stay |
| 4 and 5 (outdoors, pool and gate) | Day 4, first hour: R isolates the house panel from the pillar and connects the outdoor sub-panel line and its protection (ELEC-EQU-31); then energizes in stages (ELEC-EQU-33). Outdoor sub-panel (*tablero seccional*) with suitable IP. T1: pool (pump outside the zones, pool panel, equipotential bonding, ELEC-ESP-7 to 9). T2: outdoor lights, porch and gate (cable suitable for burying in conduit, IP boxes, no buried splices, ELEC-ESP-30, ELEC-CON-19). Each one with their padlock on their circuit's PIA: it protects the field cable, not the inside of the panel. Every connection inside the house panel or the sub-panel is made in a window with that panel isolated upstream. R measures and closes out each circuit (ELEC-EQU-11) | T1, T2 (R coordinates, measures and verifies) | Indoor circuits; gate by hand (manual release) until its circuit is closed out; pool out of use | `under_repair` → `repaired` → `verified` |
| 6 (indoor circuits with faults) | Indoor circuits that came out `fault` (for example, the ones taken out of service in the music room, laundry, garage): section-by-section search (ELEC-DIA-4), repair or rewire (ELEC-EQU-10). Any remaining crossed neutrals are separated: the field part with the circuit locked; the part in the panel, in a window with the panel isolated from the pillar (ELEC-EQU-31) | T1, T2, R | Everything `verified` | Same as above |
| 7 (closeout and test report) | Final measurements of all circuits, ID with tester, earthing, leakage per ID with clamp meter (ELEC-EQU-3), phase balance, printed labels, single-line diagram on the door (`plan single-line`), final drawing (`plan draw`, `plan dxf`), handover documentation (ELEC-MED-11), explanation to the owner (monthly test button, ELEC-MED-15) | R (T1 and T2 finish details and tidying) | Everything | All `verified`; final `plan summary` |

Commands the agent uses in this case (examples, job `patched-house`):
```bash
gateway electricidad plan new patched-house
gateway electricidad plan validate /workdir/electricidad/patched-house/survey.json
gateway electricidad plan draw /workdir/electricidad/patched-house/survey.json --floor PB --color status --format png
gateway electricidad plan single-line /workdir/electricidad/patched-house/survey.json
gateway electricidad plan sheets /workdir/electricidad/patched-house/survey.json --tech "T1"
gateway electricidad plan draw /workdir/electricidad/patched-house/survey.json --only POOL --format pdf
gateway electricidad plan status /workdir/electricidad/patched-house/survey.json POOL under_repair --tech "T1" --note "pump box with water"
gateway electricidad plan summary /workdir/electricidad/patched-house/survey.json
gateway electricidad plan dxf /workdir/electricidad/patched-house/survey.json
```
The outputs go to `/workdir/electricidad/patched-house/output/` and the agent sends them to the group over Telegram. The
commands follow the contract in [surveys-and-drawings.md](surveys-and-drawings.md) and were run against the tool on a copy of
the house example (`examples/house-panel-photo.json`, with the pool circuit as `POOL`).

### With more or fewer people
- **2 people:** R also has a package; days 4 to 6 take longer. The two never work on the outdoor sub-panel and on the panel at the same time without group lockout. Switching, work inside the panel and live measurements are done together (ELEC-EQU-35).
- **4 to 6 people:** R has no package of their own. Two pairs in parallel (outdoors and pool / indoors) from day 4; with 6, each pair has a leader and R coordinates the whole (ELEC-EQU-12). Sectioning (days 3 and 3b) does not speed up much with more people: only two people fit at the panel.

## Templates
The agent fills them in and prints them in the crew's language.

### Electrical work permit (1 page, one per working day and per job)
```text
ELECTRICAL WORK PERMIT, DE-ENERGIZED                          No. ____   Date ____/____/____
Job (no personal data): ______________________   Address for emergencies: ______________
Person responsible for the work (and for the task): ____________________  (the only one who switches and re-energizes)   Signature: ________
Coordinator (if there are 2 crews): ____________________
Authorized to measure live (ELEC-EQU-32): ____________________
Transfer of responsibility: from __________ to __________  time ____  signatures ________ / ________

1. TODAY'S WORK
   Packages / circuits (survey ID): ______________________________________________
   Work inside the panel (window and who): ____________________________________________
   Out of scope today (not touched): ______________________________________________________

2. ISOLATION AND LOCKOUT POINTS (operations padlocks; keys in group lockbox No. ____)
   [ ] Main panel (pillar) - device: ________   padlock: ____
       (MANDATORY if anyone works inside the house panel, ELEC-EQU-31)
   [ ] House panel - main switch: ________    padlock: ____
   [ ] Outdoor sub-panel / others: ________________    padlock: ____
   Terminals that cannot be isolated, covered with a shield at: ____________________
   Back-feed sources checked: [ ] generator set  [ ] UPS  [ ] panels/inverter
   [ ] other panel/other phase  [ ] capacitors  [ ] none (confirmed with: ___________)
   Temporary supply and pillar branch live (where): ____________________
   Individual lockouts fitted before removing the group one (ELEC-EQU-33): ______________

3. VERIFICATION
   Absence of voltage verified by the person responsible at: __________  Time: ____
   (includes the neutral and, if working in the panel, the incoming terminals of the main switch and the ID)
   Detector No. ____ proved before [ ] and after [ ]
   Earthing and short-circuiting: [ ] fitted at ________
   [ ] omitted at the discretion of the H&S officer (Dec. 911/96 art. 79 a) III requires it): ____

4. TEAM (each person: personal padlock in the lockbox + verification at their own point)
   Name        Role       Package   Padlock No.   Cover (ART/insurance)    Verified at their point (where, time)   In      Out    Signature
   _________   ________   _______   ___________   ______________________   _____________________________________   _____   ____   _________
   _________   ________   _______   ___________   ______________________   _____________________________________   _____   ____   _________
   _________   ________   _______   ___________   ______________________   _____________________________________   _____   ____   _________

5. START-OF-DAY BRIEFING   [ ] what is energized  [ ] packages  [ ] lockouts  [ ] back-feeds
   [ ] height/drilling/rain  [ ] occupants/pool  [ ] PPE and instruments
   [ ] companion for tasks not done alone (ELEC-EQU-35)  [ ] time work stops today
   Emergency isolation points today: ______________________________________________________
   Emergencies: who isolates: ________  who calls: ________  who meets them at the door: ________
   Phones: emergency ______  ART ______  utility ______   First-aid kit at: ______

6. CLOSE-OUT AND RE-ENERGIZING (completed by the person responsible)
   [ ] personal padlocks removed (all)  [ ] people counted: ____  [ ] walk-round done
   [ ] tools, leftovers, signs and earths removed  [ ] insulation measured on what was touched
   [ ] neutrals reconnected and tightened (list checked)  [ ] L-N per phase: R ___ S ___ T ___ V
   Energized: __________ Time: ____   Remains locked out (out of service): ______________
   Notes / padlock removed by procedure (ELEC-EQU-22): ___________________________
```

### Lockout tag (one per person and per padlock)
```text
┌─────────────────────────────────────────┐
│         DANGER - DO NOT OPERATE         │
│      PERSON WORKING ON THIS CIRCUIT     │
│                                         │
│ Name: ________________________________  │
│ Company / crew: ______________________  │
│ Contact: _____________________________  │
│ Circuit / device: ____________________  │
│ Date: ____/____/____   Time: ________   │
│ Person responsible for the work: _____  │
│                                         │
│ Only the person named may remove this   │
│ padlock and this tag (except under      │
│ procedure ELEC-EQU-22).                 │
└─────────────────────────────────────────┘
```
Variant for the person in charge at the end of the working day: "FUERA DE SERVICIO - TRABAJO EN CURSO - NO ENERGIZAR" (out of service, work in progress, do not energize), with the
same data block.

### Circuit closing checklist
| # | Check | Criterion | Rule |
|---|---|---|---|
| 1 | Work finished | Outlet points and boxes with covers; nothing loose; splices only in boxes and with connectors | ELEC-CON-21 |
| 2 | Cross-section and protection | The PIA matches the cable cross-section (`gateway electricidad coordinate`) | ELEC-PRO-4, ELEC-REV-11 |
| 3 | Own neutral | No continuity with the set of the other neutrals; all its outlet points work with its neutral alone; it comes from its group's ID | ELEC-EQU-5, ELEC-TAB-16 |
| 4 | Neutral reconnected and tightened | On its own two-pole MCB or on its ID's terminal block, manufacturer's torque, label fitted | ELEC-EQU-34, ELEC-TAB-14 |
| 5 | Insulation | L-PE, N-PE and L-N ≥ 1 MΩ at 500 V DC and in the same range as the healthy circuits | ELEC-MED-4 |
| 6 | PE continuity | Every earthed socket outlet and every exposed conductive part connected to the PE | ELEC-MED-3 |
| 7 | Polarity | The phase goes to the light switch (no switch breaks the neutral) and to the correct terminal of the socket outlet | ELEC-MED-7, ELEC-EQU-25 |
| 8 | Outdoor / damp | IP for the location, suitable cable, sealed entries | ELEC-ESP-28, ELEC-ESP-30 |
| 9 | Re-energizing | Personal padlocks removed, people counted, the person in charge energizes; in three-phase, even L-N on each phase before connecting loads | ELEC-EQU-17, ELEC-EQU-33 |
| 10 | Group ID | Trips with a tester within time and current; test button | ELEC-MED-6 |
| 11 | Operation | Each outlet point tests fine; no trips under load | ELEC-MED-12 |
| 12 | Record | Measurements entered; `plan status ... verified` by the person in charge; label on the panel | ELEC-EQU-11, ELEC-EQU-14 |

## What this guide does not replace
- The design of the renovation, the execution and the signature (and the documentation filed with the utility (*distribuidora*) or the municipality when applicable) are done by a professional or installer qualified in the jurisdiction; see [regulations-and-permits.md](regulations-and-permits.md).
- If there are employees on payroll or the job is classed as construction, the Safety Program, the site safety file (*legajo técnico*), the training, the written lockout procedure, the PPE selection, the classification of live measurements and the decision to omit temporary earthing on a circuit with no back-feed are defined and signed by the health and safety officer together with the ART (workers' compensation insurer).
- Live work (Res. SRT 3068/2014) is a separate trade, with a specific qualification: this guide does not cover it.
- What is before the meter (service connection (*acometida*), meter, terminal block and seals) belongs to the utility: if it has to be isolated there, the utility does it.
- OSHA and NFPA 70E are cited as good practice; they are not enforceable in Argentina. AEA, IRAM and IEC standards are paid: detailed values must be confirmed in the current edition.
- The plan by working day and the split of RCDs in this case are an example for one photo: the actual split comes from the measurements on site.
- In an emergency, the instructions of the emergency services prevail.
