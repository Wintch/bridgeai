---
title: Reviewing an existing panel (in person or from a photo)
scope: visual inspection of panels in houses, apartments, small shops and common services in Argentina; what can be concluded from a photo sent by chat, how to read the front of MCBs (PIA) and RCDs (ID), checklist by severity, worked example with a real panel, and the format of the report the agent returns
when_to_use: someone sends a photo of their panel and asks "is it OK?"; you are going to look at a panel before quoting, buying a house or extending; an RCD (ID) trips and you want to look at the panel before measuring; you have to decide what is urgent and what can wait
related: [README.md, regulations-and-permits.md, grades-and-circuits.md, conductors-and-conduits.md, protection.md, earthing.md, panels.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md]
as_of: 2026-11-15
sources: [AEA 90364-7-770 Ed. 2017 (clauses cited; Ed. 2026 is already published, digital on sale and print delivered from 2026-11-16, per aea.org.ar consulted 2026-11-15), AEA 90364-7-771 Ed. 2006 (apartments), AEA 90364-7-772 Ed. 2019 (common services), AEA 90364-7-701 Ed. 2012 (bathrooms), AEA 90364-7-702 Ed. 2018 (swimming pools), AEA 95150 Ed. 2007 (LV supply and metering), AEA 90364-6 Ed. 2025, IEC 60898-1 (MCB marking), IEC 61008-1 Ed. 4.0 2024 and IEC 61009-1 (RCD marking), Res. SIyC 237/2024 + Disp. 1/2024 + Res. 428/2025 (conformity marking, argentina.gob.ar consulted 2026-11-15), Res. SIyC 236/2024 (Anexo II per Res. SIyC 26/2025) + Disp. DNRT 2/2025 (materials up to 63 A, via ELEC-NOR-14), Res. ENRE (now ENReGE) 225/2011 and 269/2012 (DCI, Edenor and Edesur area), Dec. 351/79 Anexo VI, Dec. 911/96 arts. 74-87, Res. SRT 3068/2014 and 900/2015]
---
# Reviewing an existing panel

How to look at a panel that is already built and say, honestly, what is right, what is wrong, what is urgent and what
cannot be known without going there. It works for the in-person review and, above all, for when the person sends **a photo
by chat**. Each rule has a stable ID (ELEC-REV-n) so the agent can cite it in its answer ("see ELEC-REV-10").
How to build a new panel correctly is in [panels.md](panels.md) (ELEC-TAB); here it is used as the yardstick to
measure what already exists.

**Which edition applies (as of 2026-11-15).** AEA has already published **Ed. 2026 of 90364-7-770** ("Viviendas
unifamiliares con consumos hasta 63 A inclusive y corriente presunta de cortocircuito ≤ 10 kA, clasificaciones BA2 y
BD1" (single-family dwellings within those load, short-circuit and external-influence limits)): the digital version is on sale at aea.org.ar and the print version is listed as pre-sale with delivery from
2026-11-16 (catalog consulted 2026-11-15). **The 770.x clauses cited in this guide are from Ed. 2017** and must be
checked against the 2026 edition: they may have changed number or content. From what date each edition is required is set by
each jurisdiction or body (municipality, utility, regulator); see ELEC-NOR-4 in
[regulations-and-permits.md](regulations-and-permits.md). Which part applies by use: **770** for the
single-family house within that scope; **771 Ed. 2006** for apartments in buildings, offices, shops and
dwellings outside the scope of 770; **772 Ed. 2019** for common services and common areas; **701 Ed. 2012**
for bathrooms and **702 Ed. 2018** for swimming pools, on top of whichever applies (ELEC-NOR-3, ELEC-REV-28). Many
clauses of 771 and 770 say the same thing under a different number; here 770 is cited because it is the one we have read.
AEA and IEC standards are paid: here the clause is summarized and cited, not copied.

**Safety first.** Reviewing means **looking**, not touching. An old panel can have exposed live terminals, a broken
neutral or a device that does not trip. Nobody removes an inner cover (dead front, *contratapa*) with the power on to take a photo, and nobody "tightens a
little screw" while reviewing. Opening the main switch does **not** de-energize its incoming terminals, or what
comes from the meter, or a device installed upstream of it (ELEC-REV-27) (see [site-safety.md](site-safety.md), ELEC-SEG-1 to 5). This guide does not cover live
work (Res. SRT 3068/2014: specific authorization).

## Quick reference
| Situation | Rules |
|---|---|
| The person is going to take photos of the panel | ELEC-REV-1, ELEC-REV-3 |
| What I can and cannot state from a photo | ELEC-REV-2 |
| Is it single-phase or three-phase? | ELEC-REV-4 |
| Reading an MCB (*térmica*, PIA) | ELEC-REV-5 |
| Reading an RCD (*diferencial*, ID) | ELEC-REV-6 |
| 2 poles, 4 poles, "1P+N"? | ELEC-REV-7 |
| Exposed terminals or busbars, missing inner cover | ELEC-REV-8 |
| Darkened cable or terminal, burning smell | ELEC-REV-9 |
| No RCD, or a single one for everything | ELEC-REV-10 |
| Large MCB on a small cable | ELEC-REV-11 |
| Moisture, wooden enclosure, unsuitable location | ELEC-REV-12 |
| No main isolation, single-pole MCBs | ELEC-REV-13 |
| Plain green, neutral in another color | ELEC-REV-14 |
| Cable jumpers, two cables per terminal, no ferrules | ELEC-REV-15 |
| Shared neutrals, mixed terminal blocks | ELEC-REV-16 |
| Mixed brands, uncertified devices, breaking capacity | ELEC-REV-17 |
| Is an SPD needed? | ELEC-REV-18 |
| Labels, single-line diagram, spare ways, tidiness | ELEC-REV-19 |
| What can only be settled by measuring in person | ELEC-REV-20 |
| Putting together the answer for the person | ELEC-REV-21, ELEC-REV-22 |
| Smoke, flame, burning smell right now | ELEC-REV-9 |
| "The enclosure gives me a tingle" | ELEC-REV-1 |
| Plug fuses or wire fuses, knife switch, wood, cloth-insulated cables | ELEC-REV-23 |
| Aluminum cables, copper-aluminum joints, "counterfeit" (*trucho*) cable | ELEC-REV-24, ELEC-REV-11 |
| Generator or solar inverter plugged into the panel | ELEC-REV-25 |
| Changeover switches, voltage protector, contactor, timer, pump controller | ELEC-REV-26 |
| Does the RCD go before or after the main switch? Two RCDs in series | ELEC-REV-27 |
| Building: which panel am I looking at and which standard applies? | ELEC-REV-28 |
| Air conditioner hung off a socket-outlet circuit | ELEC-REV-29 |

## What you can and cannot see in a photo

| Can be seen (if the photo is sharp) | Cannot be known from the photo |
|---|---|
| Brand, line and model of each device | Whether the device is genuine or a well-made counterfeit |
| Rated current and curve (C10, C16...) | Whether it trips when it should (that is tested, ELEC-MED-6) |
| Breaking capacity printed in a box (3000, 4500, 6000) | The prospective short-circuit current at the site (the utility provides it) |
| IΔn, type and current of the RCD | Whether the RCD really covers all circuits (depends on the wiring behind) |
| Number of poles, number of RCDs, whether there is a main switch | The real cross-section of each cable (the legend is on the insulation, almost never in view) |
| Cable colors, plain green, green-yellow | Whether the earth bar reaches an earth rod (*jabalina*) and what it measures (Ω) |
| Cable jumpers or busbar comb (*peine*), loops, mess | Terminal tightness (torque) |
| Whether the inner cover or blanking plates are missing | Crossed or shared neutrals downstream |
| Labels and their legibility | Leakage, insulation, voltage drop |
| Obvious signs of heat (brown, melted plastic, soot) | Incipient heating behind the device |
| Moisture, rust, wooden enclosure | Whether the metal enclosure has its door earthed |
| Position of each lever (I-ON / O-OFF) | Which circuit each MCB really feeds (labels are often wrong) |

Practical rule for the agent: everything in the right-hand column goes in the report as **"to verify in person"**,
never as a statement.

## Before looking

### ELEC-REV-1: The photo is taken by someone without touching anything dangerous
- **Rule:** someone who is not an electrician is asked **only** to open the panel door and take photos. They are **not** asked to remove the inner cover, unscrew anything, move cables, or switch MCBs off or on "to see what goes off" with people using the house.
- **Why:** removing an inner cover with the power on leaves terminals and busbars within reach of the hand and the screwdriver. A person without training does not have the equipment (gloves, insulated tools, CAT III/IV instrument) or the practice to do it without risk.
- **How:** ask for photos with the door open and the inner cover **as it is**. Dry hands, not leaning on the enclosure, with light (phone flashlight from the side to avoid glare). If the panel already has no inner cover, have them take the photo **from one step away**, without bringing fingers or the phone close to the terminals; the close-ups of ELEC-REV-3 are taken with the phone's **zoom** from that same spot, never by moving closer. If the person removed the inner cover or "it was like that": they must **not** put it back or screw it on with the panel energized (that is work inside the panel, ELEC-EQU-31); meanwhile, door closed, nobody opens it except to operate an MCB, and an electrician fits it with the panel isolated upstream (ELEC-REV-8).
- **Verify:** before asking for more photos, ask: (1) whether there is a burning smell, smoke, sparks or noises (buzzing, crackling): if so, go straight to ELEC-REV-9; (2) whether they have ever felt a **tingle or "kicks"** when touching the enclosure, the panel door, taps or appliances. If they say yes, they must **not touch the enclosure** or open the door, the photo is not needed, and they should call an electrician: a metal enclosure without earth (or without an RCD that trips) can have its exposed metal live, and opening the door means touching it (see ELEC-DIA-16 in [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Don't:** ask "take the cover off so I can see the cables"; ask them to touch a cable to see if it is hot; insist on the photo if there was a tingle.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (covers and inner covers removable only with a tool; no live part accessible with the door open), to be checked against Ed. 2026; Dec. 351/79, Anexo VI (dead work and lockout in workplaces); Res. SRT 3068/2014, which adopts AEA 95705 (live work up to 1 kV, authorized personnel only); on construction sites, Dec. 911/96 arts. 74-87 (construction industry regulation). In a dwelling in use these labor rules are taken as a safety criterion, not as an obligation of the homeowner. See ELEC-SEG-1, ELEC-SEG-2, ELEC-NOR-6.

### ELEC-REV-2: Separate what is seen from what is deduced, and state the level of certainty
- **Rule:** for each finding, say whether it is **seen** (readable in the photo), **deduced** (inferred on good grounds) or **not verifiable** from the photo. What cannot be read is marked "illegible"; it is not filled in with the "most likely" value.
- **Why:** the person is going to decide (spend money, call someone, stop worrying) based on what you say. An "it's fine" said from a photo about something that cannot be seen (the earth, the cross-section, the tightness) is false reassurance; an "it's all wrong" without grounds scares people and discredits you.
- **How:** use the three labels in the report (ELEC-REV-21). Examples: "PIA C40 4 polos rotulado TERMICA GRAL" (labeled main breaker) (seen); "the supply is three-phase" (deduced, from the 4-pole devices); "the cross-section of that MCB's cable" (not verifiable). For small or blurry numbers, write the reading and the doubt: "C15 (could be C25)".
- **Verify:** reread the report before sending it: no statement about earth, cross-section, torque or RCD operation without the word "verify".
- **Don't:** estimate the cross-section "from the thickness in the photo" as if it were data; invent the text of a smudged label; certify anything.
- **Source:** this guide's criterion, aligned with the visual inspection in AEA 90364-6 (Ed. 2025) and 770.19, which separates visual inspection from tests (see ELEC-MED-1, ELEC-MED-2).

### ELEC-REV-3: Ask for the photos that are useful
- **Rule:** for a remote review ask, at a minimum, for: (1) the whole panel with the door open; (2) close-ups of each row of devices, straight on and sharp; (3) a close-up of the front of the RCD or RCDs; (4) the outside of the enclosure (door, frame, surroundings: wall, moisture, what is nearby); (5) if it can be done without risk, the meter or the meter cabinet (to know whether it is single- or three-phase); (6) if there is a single-line diagram or drawing on the door, a photo of it.
- **Why:** with a single general photo curves and currents cannot be read; with close-ups but no general photo you cannot tell how they are grouped. The RCD data is usually in small print.
- **How:** ask for the photo to be straight on (not at an angle), without direct flash if the plastic shines, and with each row fully in frame. If the panel has no inner cover, the close-ups are taken with zoom from one step away (ELEC-REV-1), not by bringing the phone closer. If a label is covered by a piece of paper, have them photograph it as it is: there is no need to peel it off.
- **Verify:** that all the devices in the general photo can be counted and that each one appears in some close-up.
- **Don't:** ask for photos of the earth rod by uncovering pits full of water, or of the meter box by breaking the utility's seals.
- **Source:** this guide's criterion.

## Reading the devices

### ELEC-REV-4: Single-phase or three-phase is recognized by the incoming device and the colors
- **Rule:** determine the type of supply before giving an opinion, because it changes what is correct.
  | Clue | Single-phase (220 V, phase + neutral) | Three-phase (3 × 380/220 V + neutral) |
  |---|---|---|
  | Main switch | 2 poles (2 modules, 2 levers joined) | 4 poles (4 modules) |
  | Incoming RCD | 2 poles | 4 poles (or several 2-pole ones spread across phases) |
  | Motor circuits, central air, large pump | 2 poles | sometimes 3 or 4 poles |
  | Phase colors arriving at the main switch | only one (any of the three) | brown, black and red |
  | Meter (without opening covers or seals) | plate: 1 phase, 220 V; 2 cables enter the meter enclosure | plate: 3 × 220/380 V, "3 fases 4 hilos" (three phases, four wires); 4 cables enter |
  | Utility bill | single-phase supply | three-phase supply |
- **Why:** in a three-phase supply the 220 V circuits are spread across the three phases; if they all end up on one, that phase is overloaded while the others carry nothing. In single-phase, on the other hand, a 4-pole device as the incoming device is a waste or an assembly error.
- **How:** with the same current, what the incoming device lets through changes a lot. Apparent power: single-phase S = U × I; three-phase S = √3 × U × I (in VA). Active power: P = S × cos φ (in W).
  - Example: 40 A main switch. Single-phase: S = 220 V × 40 A = **8 800 VA ≈ 8.8 kVA** (≈ 8.8 kW with cos φ = 1; with cos φ = 0.9, P = 8 800 × 0.9 = **7 920 W**). Three-phase: S = 1.732 × 380 V × 40 A = **26 327 VA ≈ 26.3 kVA** (with cos φ = 0.9, P = 26 327 × 0.9 = **23 694 W ≈ 23.7 kW**).
  - Careful: that is what the main switch lets through before tripping on overload, **not** the contracted power; the power that can be used is set by the contract with the utility (bill) and its protection at the service connection. The agent does these calculations with `gateway electricidad` (current/power), not from memory.
- **Verify:** in person, with a CAT III/IV instrument and by trained personnel, voltage between phases ≈ 380 V and phase-neutral ≈ 220 V in three-phase (see ELEC-MED-7).
- **Don't:** deduce "three-phase" just from seeing red and black cables (in single-phase the phase can be any of the phase colors); assume that a panel with a 4-pole RCD has the phases well balanced.
- **Source:** AEA 90364-7-770:2017, 770.16.5.1 and 770.16.5.3 (2-pole incoming device in single-phase, 4-pole in three-phase); colors: 770.10.3.8.5 and table 770.10.XIII (see ELEC-CON-7); meter and service connection: AEA 95150 Ed. 2007 and the utility's specification (ELEC-NOR-15). Power formulas: basic electrical engineering.
### ELEC-REV-5: Read the front of an MCB (*térmica*, PIA)
- **Rule:** for each PIA write down: **rated current and curve**, **breaking capacity**, **number of poles**, **standard** and **conformity marking**. If something cannot be read, "illegible".
- **What each marking means:**
  | Marking on the front | Meaning | Example |
  |---|---|---|
  | Letter + number | Magnetic tripping curve + rated current In | **C16** = C curve, 16 A |
  | Number in a box, no unit | Rated breaking capacity Icn, in amperes | **3000** = 3 kA; **4500** = 4.5 kA; **6000** = 6 kA |
  | Small number in a little square | Energy-limiting class | **3** (the best in the standard) |
  | 230/400 V~ or 240/415 V~ | Rated voltage | |
  | IEC 60898-1 (there is no current IRAM standard: IRAM 2169 is withdrawn, ELEC-IRA-7) | MCB standard for household and similar use | |
  | IEC 60947-2 | "Industrial" standard: other tests and marking (Icu, Ics) | |
  | AR with double tick + QR (or the earlier S mark) | Argentine conformity marking | |
- **Curves:** instantaneous (magnetic) tripping happens between **3 and 5 × In** on a **B** curve, between **5 and 10 × In** on a **C** curve and between **10 and 20 × In** on a **D** curve. In dwellings the normal choice is **C**; B on long circuits or with low fault current; D only for loads with very heavy inrush, to be justified.
  - Example: a C16 must **not** trip instantaneously below 5 × 16 = **80 A** and **must** trip from 10 × 16 = **160 A**; between those two values it may or may not. To ensure instantaneous tripping on a fault, the fault current has to reach 160 A.
- **Why:** In tells you which cable it can protect (ELEC-REV-11); the breaking capacity tells you whether it withstands a short circuit at that point without exploding; the curve tells you whether it will trip on a distant fault.
- **How:** about unusual values: **15 A** is not among the preferred values of IEC 60898-1 (6, 8, 10, 13, 16, 20, 25, 32, 40, 50, 63 A...), but it is made in Argentina and is common in panels a few years old; it is not a defect in itself, it is judged against the cable. The levers usually carry "I-ON" and "O-OFF": the position is read on the lever or in the small window.
- **Verify:** that the breaking capacity box exists (a PIA without Icn printed is suspicious, ELEC-REV-17) and that its value is ≥ the prospective short-circuit current the utility (distribution company) reports for that point.
- **Don't:** confuse the number in the box (breaking capacity) with the current; accept a curve that cannot be read.
- **Source:** IEC 60898-1 (marking, preferred values of In, B/C/D instantaneous tripping ranges and limiting classes), summarized; AEA 90364-7-770:2017, 770.16.5.2 (PIA per IEC 60898-1). Conformity marking: Res. SIyC 237/2024, Disp. 1/2024 and Res. 428/2025, per argentina.gob.ar, "Marcado de conformidad" (conformity marking) (required for sale from 2025-10-01; consulted 2026-11-15; see ELEC-REV-17). There is no current IRAM standard for PIA: IRAM 2169 is listed as withdrawn in the IRAM catalog, and a device that only says "IRAM 2169" carries an old reference ([iram-standards.md](iram-standards.md) ELEC-IRA-7). **Not verified in a primary source:** whether AEA sets an absolute minimum breaking capacity for dwelling PIAs (3 kA is seen in practice; see [protection.md](protection.md)).

### ELEC-REV-6: Read the front of an RCD (*disyuntor* / *diferencial*, ID)
- **Rule:** for each ID write down: **In** (rated current), **IΔn** (sensitivity), **type** (AC, A, F, B), **S** if it is selective, **number of poles**, **conditional short-circuit current** (Inc or IΔc) and the **backup protection** it requires (SCPD), **standard** and marking.
- **What each marking means:**
  | Marking | Meaning | What you look for |
  |---|---|---|
  | In 25 / 40 / 63 A | Current that can flow continuously (it is not overload protection) | ≥ the MCB in series upstream, or ≥ the sum of the MCBs below (ELEC-TAB-10) |
  | IΔn 0.03 A (30 mA) | Leakage current at which it must trip | **≤ 30 mA** on final circuits |
  | Plain sine-wave symbol | Type **AC**: sinusoidal alternating leakage | The most basic |
  | Sine wave + half wave | Type **A**: also pulsating leakage (electronics, small drives) | Recommended where there is electronics |
  | F / B | For single-phase drives (F) or with smooth DC (B: EV chargers, inverters, per manufacturer) | See [special-installations.md](special-installations.md) |
  | **S** in a box | Selective (time-delayed), for use upstream of other IDs | Never as final 30 mA protection |
  | Inc or IΔc in a box (e.g. 3000, 6000, 10000) | Short circuit it withstands **if** protected by the indicated SCPD | Coordination with the MCB: manufacturer's table |
  | Im / IΔm | Rated making and breaking capacity of the ID itself | Minimum value in the standard: the greater of 10 × In and 500 A |
  | SCPD / "fus 63 A" | Backup protection it was tested with (fuse or PIA) | If the installation has an MCB, ask for the coordination table |
  | IEC 61008-1 | ID **without** overcurrent protection | Needs an associated MCB |
  | IEC 61009-1 | ID **with** overcurrent protection (combined, RCBO) | In single-phase, with both poles protected (ELEC-TAB-9) |
  | T button / "probar mensualmente" (test monthly) | Mechanical test | Have the person test it as often as the manufacturer indicates (in general, once a month), only if they can reach the button without bringing their hand near live parts (ELEC-REV-22) |
- **Why:** the ID is the protection that trips when a person touches a phase and the current flows to earth through their body; in a TT system it is also the protection against indirect contact. It is a **supplementary** protection: it does **not** protect if you touch phase and neutral at the same time (the current returns through the neutral and the ID sees no difference), nor against leakage below its threshold; that is also why it does not permit live work. An ID with a small In and a heavy load overheats without tripping, because it has no thermal protection.
- **How:** example of the In check: 4-pole 63 A ID with a C40 main switch upstream: 40 A ≤ 63 A, it complies by the series-device criterion even if the sum of the MCBs below exceeds 63 A. For Im: a 63 A ID has at least 10 × 63 = **630 A**.
- **Verify:** in person, test with an IEC 61557-6 tester at 0.5 IΔn, IΔn and 5 IΔn (ELEC-MED-6). The button only tests the mechanism.
- **Don't:** accept a 300 mA (or selective) ID as final protection for socket outlets and lighting; treat a 61008 as if it protected against overload.
- **Source:** AEA 90364-7-770:2017, 770.14.2.3 (30 mA non-delayed on final circuits), 770.14.3.2 (TT: protection by RCDs; 300 mA selective between panels), 770.15.2.2.5 (rated current and short circuit of the ID); IEC 61008-1 Ed. 4.0 (2024) and IEC 61009-1 (marking, types, minimum Im), summarized; monthly test with the button: manufacturer's instruction (the ID in the example photo says "Prueba mensualmente" (test monthly); see ELEC-PRO-13); in workplaces, Res. SRT 900/2015, art. 4, requires periodic checking of protective devices against indirect contact, without setting a frequency. 770 clauses: Ed. 2017, to be checked against Ed. 2026. **Not verified in a primary source:** whether 770 Ed. 2017 requires type A on any dwelling circuit; the international trend (IEC 60364-5-53) restricts type AC to loads without DC components.

### ELEC-REV-7: Tell apart 2-pole, 4-pole, "1P+N" and single-pole
- **Rule:** count **modules** (each 18 mm), **levers** (joined by a small bar if multipole), **terminal screws** at top and bottom, and look for the marking ("2P", "4P", "4 polos", "N").
  | Device | Modules | Terminals top / bottom | Comment |
  |---|---|---|---|
  | Single-pole (1P) | 1 | 1 / 1 | **Prohibited** in single-phase dwellings (breaks only one conductor) |
  | 1P+N (switched-through neutral) | 1 or 2 | 2 / 2, one pole marked N without protection | **Prohibited** in single-phase by 770 |
  | Two-pole (2P) | 2 | 2 / 2 | Correct in single-phase |
  | Three-pole (3P) | 3 | 3 / 3 | Three-phase motors without neutral |
  | Four-pole (4P) | 4 | 4 / 4, sometimes one pole marked N | Three-phase incoming device |
- **Why:** with a single-pole device or a "switched-through neutral" the "isolated" circuit can stay live if phase and neutral come reversed from the network or if the neutral becomes live.
- **How:** on the RCD, the diagram on the front shows the poles and the test circuit; on a 4-pole ID used in single-phase, the test button may not work if the poles indicated by the manufacturer were not connected.
- **Verify:** that each 220 V circuit has its 2-pole PIA and that the incoming device has as many poles as live conductors (2 or 4).
- **Don't:** confuse two single-pole devices side by side (separate levers) with a two-pole device; nor an improvised tie bar with a factory two-pole device.
- **Source:** AEA 90364-7-770:2017, 770.16.5.1 (prohibition of single-pole, 1P+N and unprotected neutral in single-phase) and 770.16.5.2 (simultaneous opening of poles). Test circuit in 4-pole IDs: **Not verified in a primary source** for each brand; check the manufacturer's sheet.

## Checklist by severity

Use it in this order. **Urgent** = risk of electrocution or fire now; **Important** = a protection is missing or there is
an error that must be corrected soon; **Improvement** = tidiness, maintenance, extensions.

| # | What to look for | Severity | Visible in photo? | Rule |
|---|---|---|---|---|
| 1 | Accessible live parts: no inner cover (dead front, *contratapa*), exposed busbars or terminals, uncovered empty module spaces, stripped cables | Urgent | Yes | ELEC-REV-8 |
| 2 | Heating: darkened insulation, brown or melted plastic, soot, smell | Urgent | Partial | ELEC-REV-9 |
| 3 | No RCD, ID bypassed, circuits outside the ID | Urgent | Partial | ELEC-REV-10 |
| 4 | Water, moisture, rust; wooden enclosure or other combustible material | Urgent | Yes | ELEC-REV-12 |
| 5 | PIA larger than what the visible cable can carry | Important (Urgent if there are signs of heat) | Partial | ELEC-REV-11 |
| 6 | A single ID for too many circuits | Important | Yes | ELEC-REV-10 |
| 7 | No main isolation; single-pole MCBs in single-phase | Important | Yes | ELEC-REV-13 |
| 8 | Devices without marking, dubious brands, insufficient or illegible breaking capacity | Important | Partial | ELEC-REV-17 |
| 9 | Shared neutrals, mixed N and PE terminal blocks | Important | Rarely | ELEC-REV-16 |
| 10 | Wrong colors: plain green, green-yellow as phase, neutral in another color | Important | Yes | ELEC-REV-14 |
| 11 | Cable jumpers instead of a busbar comb (*peine*); two cables per terminal; flexible cables without ferrules | Important / Improvement | Partial | ELEC-REV-15 |
| 12 | Missing SPD (*DPS*) where required | Important (depending on the case) | Yes | ELEC-REV-18 |
| 13 | Unidentified circuits, no single-line diagram, no spare ways, messy wiring | Improvement | Yes | ELEC-REV-19 |
| 14 | Plug fuses or fuses reinforced with wire, open knife switches, cloth- or rubber-insulated cables | Urgent (wire, exposed knife switch) / Important | Yes | ELEC-REV-23 |
| 15 | Aluminum in the panel or Cu-Al joints without a bimetallic connector | Important (Urgent if there are signs of heat) | Partial | ELEC-REV-24 |
| 16 | Generator or inverter connected without an interlocked changeover switch | Urgent | Partial (ask) | ELEC-REV-25 |
| 17 | ID upstream of the main switch without knowing what protects it; two 30 mA IDs in series | Important / To verify | Partial | ELEC-REV-27 |
| 18 | Air conditioner on a general socket-outlet circuit | Important | Partial | ELEC-REV-29 |

### ELEC-REV-8: Live parts within reach are the first thing to report
- **Rule:** if with the door open you can see copper, a terminal, an uncovered neutral or earth bar, a busbar comb without an end cap or an uncovered empty module space, the finding is **urgent**.
- **Why:** anyone opens the panel door (a child, someone going to reset an MCB in the dark). 770 requires that with the door open there be no accessible live parts and that barriers be at least IP3XD (a 1 mm wire cannot get in).
- **How:** in the photo, look for: terminal screws visible above and below the devices (indicates there is no inner cover), bare brass bars, gaps in the row without a blanking plate, cables with a stripped end outside a terminal. Recommendation: inner cover cut to size, blanking plates, busbar covers; meanwhile, panel closed and nobody opens it except to operate it.
- **Verify:** in person, that the inner cover exists, is fixed with screws (comes off only with a tool) and does not have enlarged cut-outs.
- **Don't:** tell the person to "put tape" over the terminals; recommend removing the inner cover to get a better look.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (IP41 or IP31D; no accessible live parts with the door open; covers only with a tool) and 770.16.4.1.1 (IP3XD); values and clauses from Ed. 2017, to be checked against Ed. 2026. For the TP in the Edenor and Edesur area, the DCI (installation conformity declaration) also requires "sin acceso a partes con tensión" (no access to live parts) and IP 41 indoors (Res. ENRE, now ENReGE, 225/2011, section II item 3; see ELEC-NOR-10). See ELEC-TAB-6.

### ELEC-REV-9: Signs of heat: switch off and call, don't "keep looking"
- **Rule:** darkened or brittle insulation near a terminal, device plastic brown, deformed or blistered, soot, smell of burnt plastic, buzzing or crackling: **urgent**. What a non-electrician reports is **what they see, smell or hear**; they are not asked to bring their hand close to feel the temperature (a PIA or ID under normal load is already warm, so the data is useless, and bringing a hand close to a panel without an inner cover is exactly what ELEC-REV-1 forbids).
  - **No smoke or flame:** if they can do it without touching damaged parts, have them switch off at the device that is **upstream of the problem** and call a qualified electrician. The main switch only isolates what is downstream of it: it does not de-energize its own incoming terminals, or an ID installed before it, or what comes from the meter (ELEC-REV-27). If the smell comes from the area of the main switch or the incoming supply, switch off at the main panel or at the switch in the meter pillar (*pilar*) or meter enclosure.
  - **With smoke or flame:** don't go near the panel. Switch off at the main panel or at the pillar or meter switch **only if it is far from the source** and you can do it without going through the smoke or touching damaged parts. Get people out, call the **fire brigade (100)** and the utility (it can cut the supply from the network). **Never water** on a panel: if an incipient fire has to be tackled, an **ABC** (powder) or **CO2** extinguisher, and only if it is small and you have an exit behind you.
- **Why:** a loose terminal or a cable too small for its MCB heats up slowly until it chars the insulation; it is a classic cause of fire and it trips neither the MCB nor the RCD. Water conducts and can electrocute whoever throws it.
- **How:** in the photo, compare the color of the insulation near the terminal with the same cable farther away; look at the terminal area of the highest-current devices (main switch, air conditioner, water heater, oven). Watch out for confusion: a brown cable is a normal phase; darkening shows as a change of tone **at the end**. If the photo is not enough, say "no signs of heat can be seen in the photo; it cannot be ruled out".
- **Verify:** in person, by an electrician: with the panel de-energized and locked out, inspection of terminals and insulation; under load, thermography or an infrared thermometer from outside the inner cover to detect hot spots (see [testing-and-commissioning.md](testing-and-commissioning.md)).
- **Don't:** ask them to touch or bring a hand close to the device or the cable; "retighten" terminals with the power on; reset an MCB that tripped together with a burning smell; throw water.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (terminals and tightening), to be checked against Ed. 2026; Decreto 911/96 (reglamento para la industria de la construcción, construction industry regulation) art. 87: when a protection operates for no known cause, detailed inspection before restoring service; in a dwelling, take it as a safety criterion; ELEC-SEG-22. Electrical fire (class C: CO2 or ABC/BC powder, never water or foam; fire brigade 100): ELEC-SEG-26 (and ELEC-SEG-23 for emergency numbers) in [site-safety.md](site-safety.md), which cites Dec. 351/79 Anexo VII and Dec. 911/96 arts. 88-91. Symptoms: trade criterion, **not verified in a primary source** as a normative list.
### ELEC-REV-10: No RCD (*disyuntor* / *diferencial*) is urgent; a single ID for everything is important
- **Rule:** every final circuit must be protected by an ID with **IΔn ≤ 30 mA, non-delayed**. If no ID can be seen, or there are circuits that clearly do not go through it, or there are signs that it was bypassed, it is **urgent**. If there is a single ID for many circuits, it is **important**: the circuits must be split.
- **Why:** the ID is what trips when a person touches a live part. With a single ID for the whole house, the sum of the normal leakage of the appliances causes "unexplained" trips, people end up bypassing it, and every trip leaves everything in the dark. The recommended standing leakage downstream of an ID is up to ~30 % of IΔn (≈ 9 mA for 30 mA).
- **How:** count the IDs and the PIAs each one has (by position and by visible jumpers). This guide's criterion: 2 to 3 circuits per ID, separating lighting from socket outlets, and outdoor, pool or pump circuits on their own ID. Check that the In of each ID complies: ≥ the MCB (*térmica*) in series upstream **or** ≥ the sum of the MCBs below. **Suspicion without seeing:** if the photo does not show circuits outside the ID but the history makes it likely ("they added MCBs because it kept tripping", MCBs of another brand below, jumpers whose origin cannot be seen), it goes under URGENT with the label [suspected, not verifiable from the photo] and it is the first thing the electrician confirms with the RCD tester; it is not downgraded to "to verify" because, if it is true, those circuits have no protection against electrocution. Example: ID 2 × 40 A with PIAs of 10 + 16 + 20 A = 46 A > 40 A: it does not comply by sum; it complies if upstream there is a main switch ≤ 40 A.
- **Verify:** in person, that each circuit trips its ID with the tester plugged into a socket outlet of that circuit (that confirms it is downstream). On lighting circuits, which have no socket outlets, the test is done at an outlet point (*boca*) or at the luminaire with an adapter or probes, connecting with the power off. If the socket outlet has no PE, the tester (IEC 61557-6, needs a reference to PE or earth) may not test or may give a false result: first the PE is sorted out (ELEC-MED-3). Leakage measurement per ID with a leakage clamp meter (ELEC-MED-6, ELEC-TAB-19).
- **Don't:** accept "I left it outside the *disyuntor* because it kept tripping"; recommend going up to 300 mA so it doesn't trip.
- **Source:** AEA 90364-7-770:2017, 770.14.2.3 (30 mA non-delayed), 770.16.5.4 and note 1 (ID per circuit or grouped; it sets no maximum), 770.15.2.2.5 (In of the ID); clauses from Ed. 2017, to be checked against Ed. 2026. In the Edenor and Edesur area: Res. ENRE (now ENReGE, formerly ENRE) 225/2011, section II item 3.8 with the text replaced by Res. ENRE 269/2012 (ID ≤ 30 mA in the main panel, protected against overload and short circuit; per note 2 of the DCI (installation conformity declaration) form, it can go in the sub-panel (*tablero seccional*)), verified in the 2022 edition text published on argentina.gob.ar per ELEC-NOR-10. 30 % of IΔn limit: IEC 60364-5-53, 531.3.2, via IET commentary (see ELEC-TAB-19); **not verified in the IEC text**. "2 to 3 circuits per ID": this guide's practical criterion.

### ELEC-REV-11: The MCB (*térmica*) protects the cable: if it is larger than the cable, it doesn't protect it
- **Rule:** the rated current of the PIA must be ≤ the corrected current-carrying capacity of the cable (In ≤ Iz). A 20 A or 25 A MCB on a 1.5 mm² cable, or 32 A on 2.5 mm², is an **important finding** (urgent if there are also signs of heat).
- **Why:** with an MCB larger than the cable, an overload heats the cable above 70 °C (the PVC limit) without the MCB tripping.
- **How:** indicative reference (single-core cables in conduit, a single circuit, 40 °C, 2 loaded conductors):
  | Cross-section | Indicative Iz | Usual maximum PIA (C curve) |
  |---|---|---|
  | 1.5 mm² | 15 A | 10 A (15 A is the borderline limit) |
  | 2.5 mm² | 21 A | 16 A or 20 A |
  | 4 mm² | 28 A | 25 A |
  | 6 mm² | 36 A | 32 A |
  | 10 mm² | 50 A | 40 A |
  With several circuits per conduit Iz drops (factor 0.80 with 2 circuits, 0.70 with 3). Example: three circuits in 2.5 mm² in the same conduit: Iz = 21 A × 0.70 = 14.7 A, and a 16 A MCB does **not** protect them. The agent uses `gateway electricidad` (cross-section and coordination) for this calculation.
- **Verify:** the real cross-section is only confirmed in person, with the power off and by an electrician. The **printed legend does not prove the cross-section**: counterfeit (*truchos*) cables are in circulation that say "2,5 mm²" and "IRAM NM 247-3" and have less copper (ELEC-FAB-7). Methods, from simplest to most reliable:
  1. **Solid wire (a single strand):** measure the copper diameter with a caliper (vernier) and calculate S = π × d² / 4. Example: d = 1.78 mm → S = 3.1416 × 1.78² / 4 = 3.1416 × 3.1684 / 4 = **2.49 mm² ≈ 2.5 mm²**; d = 1.38 mm → S = 3.1416 × 1.9044 / 4 = **1.50 mm²**; d = 1.60 mm → **2.01 mm²**: a "2.5" that measures 1.60 mm is suspicious.
  2. **Flexible cable (many strands, the most common on site):** don't measure the diameter of the bundle (the strands deform and it misleads). S = no. of strands × π × d_strand² / 4. Example: 50 strands of 0.25 mm → 50 × 3.1416 × 0.0625 / 4 = **2.45 mm²**. Alternative: weigh 1 m of stripped copper (≈ 8.9 g per mm² per meter: a 2.5 mm² is around **22 g/m**; ELEC-CON-1 in [conductors-and-conduits.md](conductors-and-conduits.md)).
  3. **The definitive one:** resistance of a known length against the maximum in IEC 60228 / IRAM NM 280 (2.5 mm² class 5: **7.98 Ω/km** at 20 °C), with a milliohmmeter (ELEC-FAB-7 in manufacturers-and-materials.md).

  If the measured cross-section is clearly less than the legend, the cable is suspect even if it says IRAM. The agent does these calculations with `gateway electricidad` (cross-section), not from memory. From the photo, at most: "the cable of that circuit looks thin for a 25 A: verify".
- **Don't:** "increase the MCB because it trips"; state from the photo that a cable is 1.5 or 2.5 mm²; accept the cross-section based only on the legend.
- **Source:** AEA 90364-7-770:2017, 770.12 and table 770.12.I (current-carrying capacity, 2 loaded conductors column), table 770.12.II (grouping), table 770.6.I (maximum protection by circuit type), to be checked against Ed. 2026; values taken from [conductors-and-conduits.md](conductors-and-conduits.md) (ELEC-CON-8). The "Usual maximum PIA" column is this guide's practical choice, not AEA text. Maximum conductor resistance: IEC 60228 / IRAM NM 280, per ELEC-FAB-7 (Prysmian data sheets Ed. 2026 and Kalop catalog). Circle area formula: geometry.

### ELEC-REV-12: Water, moisture and combustible enclosures
- **Rule:** a panel with water, damp stains, rust on rails or terminals, or made of **wood** or another combustible or hygroscopic material, is **urgent**. A panel in the bathroom, inside a closet, over the countertop or covered by furniture is **important**.
- **Why:** moisture lowers insulation, oxidizes contacts and can energize exposed metal parts; wood chars with the heat of a loose terminal and feeds the fire. The panel must be easy to find and operate quickly.
- **How:** look at the back and the frame (rust, scale, drip marks), the wall around it and what is above it (water pipes, windows). Recommendation: a standard, certified enclosure (insulating Class II or metal with earth), in a dry, accessible place.
- **Verify:** in person, insulation resistance with a megohmmeter (megger) (ELEC-MED-4) if there was water; earth continuity of the door and the body if it is metal (ELEC-TAB-5).
- **Don't:** dry it with a hair dryer and switch the power back on; accept "wood is a good insulator".
- **Source:** AEA 90364-7-770:2017, 770.16.2.1 (dry place, not in bathrooms or furniture), 770.16.4 (non-flammable, non-hygroscopic material, mechanically rigid), to be checked against Ed. 2026; bathrooms: AEA 90364-7-701 Ed. 2012 (bathroom zones and switchgear allowed in each; see ELEC-ESP-3 and ELEC-ESP-4 in [special-installations.md](special-installations.md)). **Not verified in a primary source:** the exact clause of 701:2012 on panels (paid standard, not consulted); the prohibition of the panel in the bathroom is cited from 770.16.2.1. See ELEC-TAB-3, ELEC-TAB-4.

### ELEC-REV-13: There must be a main isolation that opens all live conductors
- **Rule:** the main panel (TP) has an **incoming circuit breaker** (main switch) of 2 poles in single-phase (4 in three-phase), and the sub-panels (TS, *tablero seccional*) an incoming device suitable for isolation. Single-pole MCBs, "1P+N" or fuses as circuit protection in the main panel are **important** findings.
- **Why:** without a main isolation the installation cannot be de-energized quickly in an emergency or for work. A single-pole device can leave the neutral live.
- **How:** look for a device labeled "general", "TG", "TERMICA GRAL" (main breaker), with a higher current than the rest. **It is not always in the first position:** sometimes an ID comes before it (in the worked example the ID is in position 1 and the main switch in 2), and then the main switch does not isolate that ID or whatever is upstream of it (ELEC-REV-27). In the **Edenor and Edesur** area (Res. ENRE 225/2011 and 269/2012), the DCI requires a two-pole thermal-magnetic breaker per circuit in the main panel and prohibits fuses as circuit protection there. In the rest of the country (Edelap, EPEC, EPE, EDEA and others), the requirements of the utility and the provincial regulator govern (ELEC-NOR-13).
- **Verify:** in person and by trained personnel, that when the main switch is opened no voltage remains on any outgoing way: absence of voltage between all live conductors and to PE, with a **contact two-pole voltage tester** (IEC 61243-3) or a CAT III/IV multimeter, proven on a live source **before and after** measuring (ELEC-SEG-5). The non-contact voltage tester (*lapicito*, *buscapolo*) or any non-contact detector is not valid for verification.
- **Don't:** take the RCD as the "main isolation" if there is no associated main MCB (the ID does not protect against overloads); assume the main switch isolates everything just because it is labeled that way.
- **Source:** AEA 90364-7-770:2017, 770.16.5.1, 770.16.5.3 (TP incoming device), 770.16.5.4 (sub-panel incoming device), to be checked against Ed. 2026; Res. ENRE (now ENReGE, formerly ENRE) 225/2011, Anexo, section II item 3, subitems 3.7 and 3.9 (two-pole thermal-magnetic breaker per circuit, no fuses), with Res. 269/2012 (DCI form), verified in the 2022 edition text on argentina.gob.ar per ELEC-NOR-10; the regulation covers Edenor and Edesur T1R users (argentina.gob.ar, "Nuevos suministros domiciliarios" (new residential supplies), consulted 2026-11-15); Edelap passed in 2011 to the jurisdiction of the Province of Buenos Aires (Decreto 1853/2011, information from secondary sources: Marval, La Gaceta); today it is regulated by OCEBA, whose 2026 resolutions cite its provincial concession contract (oceba.gba.gob.ar). Verification of absence of voltage: ELEC-SEG-5 and ELEC-NOR-6. See ELEC-TAB-9, ELEC-TAB-10.

### ELEC-REV-14: Colors: green-yellow is only earth and plain green is not used
- **Rule:** phase brown, black or red; neutral light blue (or blue); protective conductor **green-yellow**. **Plain green** or **plain yellow**, green-yellow used as phase, or light blue used as phase are **important** findings.
- **Why:** color is the first barrier against the mistake of the next person who works on it. In old installations plain green was used as earth; today it is prohibited for any function, and a plain green can be earth, a return or anything.
- **How:** in the photo count how many plain greens there are and where they go (to a bar, to a device). Usual recommendation: replace the greens in the panel with green-yellow when the wiring is redone, or at a minimum identify the ones that are PE with green-yellow rings or sleeves at both ends, after verifying that they are.
- **Verify:** in person and with the power off, what each green connects (continuity to the earth bar and to exposed metal parts).
- **Don't:** assume every green is earth; "paint" a cable with tape to change its function.
- **Source:** AEA 90364-7-770:2017, 770.10.3.8.5 and table 770.10.XIII (see ELEC-CON-7, ELEC-TAB-17).

### ELEC-REV-15: Busbar comb (*peine*) instead of cable garlands, one cable per terminal, ferrules on flexible cables
- **Rule:** with **more than 3 outgoing circuits**, distribution between devices is done with a **busbar comb** or bars, not with cable jumpers. One cable per terminal (unless the terminal is designed for two). Flexible cable with a **ferrule**. Cable jumpers on long rows and two cables per terminal are **important** findings; missing ferrules, **improvement** (or important if there are loose strands).
- **Why:** each cable jumper adds two connections; in a row of 10 devices, the current of the whole row goes through the first terminals, which work with two cables each. A flexible cable without a ferrule splays into strands and loosens.
- **How:** in the photo, jumpers look like little "loops" of cable between the top terminals of neighboring devices. Also check the color of the jumpers (if the whole row is on the same phase color, in three-phase it may indicate imbalance; ELEC-REV-4).
- **Verify:** in person and with the power off: cross-section of the jumpers (they must carry the current of the group's incoming device), terminal torque per the manufacturer, ferrules.
- **Don't:** recommend adding more jumpers for "one more MCB"; mix combs of another brand that do not fit.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (interconnection with cables only up to 3 outgoing circuits; a single conductor per terminal), Ed. 2017 via [panels.md](panels.md), to be checked against Ed. 2026. Ferrules: manufacturers' recommendation, **not verified** as AEA text (see ELEC-TAB-13, ELEC-TAB-14).

### ELEC-REV-16: Each circuit with its own neutral, and separate N and PE terminal blocks
- **Rule:** each circuit has its own neutral, which leaves from its PIA and from the same ID as its phase; neutral and earth on separate, identified terminal blocks. Shared neutrals or bars where N and PE are mixed are **important**.
- **Why:** a neutral shared between different IDs trips both (each one "sees" a leakage) and, when a circuit is opened, its neutral may still carry current. In a TT system, joining N and PE in the user's panel is an error.
- **How:** from the photo it is almost never seen with certainty; at most: light-blue cables going to a bar together with greens, or a single bar for everything. If the person says an ID trips when something on another circuit is switched on, suspect crossed neutrals (see [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Verify:** in person, with the power off and locked out: continuity between neutrals of different circuits; and insulation or continuity between the N bar and the PE bar **with the incoming device open, checking that it breaks the neutral, or with the incoming neutral disconnected**. If the neutral is still connected to the network, the measurement shows false continuity through the utility's earthed neutral and the earth rod (*jabalina*) (in TT the earth closes the path), and the reading is useless.
- **Don't:** state "it has shared neutrals" just from seeing many light-blue cables together.
- **Source:** AEA 90364-7-770:2017, 770.16.4 (identified PE terminal block), 770.3 and 770.14.3.2 (TT); RCD operating principle (IEC 61008-1). See ELEC-TAB-15, ELEC-TAB-16.

### ELEC-REV-17: Certified devices, from a compatible line, with sufficient breaking capacity
- **Rule:** PIAs, IDs and switches must have a legible standard and ratings and some certification mark of their period (safety "S" mark or IRAM on old ones; AR with double tick and QR on those sold from 2025-10-01). The new marking is required **when buying or installing** a device, not for what was already installed: a good 2015 MCB without a QR does not have to be replaced for that reason. Devices **without any mark**, with smudged data, or very different models mixed together are **important**; the breaking capacity must be ≥ the prospective short-circuit current at the site.
- **Why:** counterfeit or untested MCBs and RCDs are a known cause of devices that do not trip. Mixing brands is not illegal, but it complicates combs and spares, and a different device in the middle of a row is usually a replacement made "with whatever was at hand".
- **How:** write down the brand and line of each device and point out the ones that do not match (lever color, typeface, shape). Ask the person for a photo of the side or front of those to look for the standard and marking. In panels a few years old it is normal not to see the QR (the new marking is required for sale from October 2025, and earlier stock is accepted with the old mark if supported by an invoice or import documentation): that does not make it illegal, but it does call for a closer look at devices without any mark. A **new** device added today must come with the new marking.
- **Verify:** scan the QR and confirm that the certificate matches that model; ask the utility for the prospective Icc if the panel is near the meter (especially in three-phase installations and in buildings).
- **Don't:** declare a device "counterfeit" (*trucho*) just because it is from a brand you don't know; accept a PIA without a printed breaking capacity.
- **Source:** marking and QR: Res. SIyC 237/2024, Disp. 1/2024 and Res. 428/2025, per argentina.gob.ar/servicio/marcado-de-conformidad (consulted 2026-11-15: "AR + doble tilde" (AR + double tick) mark with QR; "desde el 1° de octubre de 2025 ningún producto certificado puede venderse sin identificación" (from 1 October 2025 no certified product may be sold without identification); stock manufactured or imported earlier, with the previous mark supported by an invoice or import documentation). Scope for PIA and ID up to 63 A: Res. SIyC 236/2024 (Anexo II in the text of Res. SIyC 26/2025: PIA 4.5.2, ID 4.5.3, combined devices 4.5.4, per [iram-standards.md](iram-standards.md) ELEC-IRA-2) and Disp. DNRT 2/2025, per ELEC-NOR-14; **not verified in a primary source** in this review (the text in the Boletín Oficial (Official Gazette) could not be opened). Breaking capacity: AEA 90364-7-770:2017, 770.16.4 (maximum design Icc marked on the panel), to be checked against Ed. 2026, and [protection.md](protection.md).
### ELEC-REV-18: SPD (*DPS*): say whether one is required, not only whether it is missing
- **Rule:** a missing **surge protective device, SPD (*DPS*, dispositivo de protección contra sobretensiones)** is **important** when the 770 Ed. 2017 requires it: always if the building has a lightning rod; if the supply is overhead (fully or partly) in areas with more than 25 thunderstorm days per year (with the exceptions in the table). That thunderstorm-days criterion may change in Ed. 2026: the current IEC 60364-4-44 moved to a risk assessment criterion. With an underground network it is not mandatory, but it may be worth it for expensive electronics (gate, pool pump with a variable-speed drive, inverter).
- **Why:** surges from lightning and switching destroy equipment, and neither the MCB (*térmica*) nor the RCD (*diferencial*) stops them.
- **How:** the SPD looks like a module with a status window (green/red) and a green-yellow conductor to the earth bar. If there is one with the window showing red, it is spent: replace it. Ask the person whether the service drop (*acometida*) is overhead or underground.
- **Verify:** in person, that there is a measured earthing (*puesta a tierra*) (an SPD without earth does not protect) and that the earth conductor is short.
- **Don't:** recommend an SPD "just because" in a panel without earth; confuse an SPD with a "protector de tensión" (voltage protector, over/undervoltage relay: it cuts on sustained undervoltage/overvoltage, a different function).
- **Source:** AEA 90364-7-770:2017, 770.15.4 and table 770.15.III (Ed. 2017, to be checked against Ed. 2026); keraunic level per AEA 92305-11 Ed. 2016. **Not verified in a primary source:** the Ed. 2026 criterion of the 770 for requiring an SPD, and the exact text of the current IEC 60364-4-44 (443, risk assessment), cited from general knowledge. See ELEC-TAB-11 and [protection.md](protection.md).

### ELEC-REV-19: Labels, single-line diagram, spare space and tidiness
- **Rule:** every outgoing circuit identified legibly and durably, single-line diagram (*unifilar*) available, **≥ 20 %** free spare space (in 18 mm modules) and tidy wiring. Whatever is missing is an **improvement**, unless the missing labels make it impossible to know what to switch off in an emergency (then, important).
- **Why:** a label that lies or a panel with no spare space ends in two conductors per terminal, extra panels hung next to it and switching errors.
- **How:** flag labels that are illegible, covered or on loose paper; devices with no label; circuits in OFF with notes like "no usar" ("do not use") (a circuit out of service that should be disconnected and labeled as spare). Recommendation: printed labels with the same name as on the drawing, and a laminated single-line diagram on the door.
- **Verify:** in person, circuit by circuit, that each PIA switches off what its label says.
- **Don't:** take a handwritten label as true; label something "varios" ("miscellaneous").
- **Source:** AEA 90364-7-770:2017, 770.16.4 (20 % spare, legends in Spanish legible at 1 m), 770.16.2.1 (electrical hazard symbol), annex 770-A.1.2 (single-line diagram); values and clauses of Ed. 2017 via [panels.md](panels.md), to be checked against Ed. 2026. See ELEC-TAB-7, ELEC-TAB-8, ELEC-TAB-18.

### ELEC-REV-20: What you can't see is measured in person, dead tests first
- **Rule:** the report from a photo **always** ends with a list of in-person checks, done by a qualified electrician (*electricista habilitado*) in this order: dead inspection → dead measurements → live tests.
- **Why:** earthing, insulation, terminal tightness and RCD operation decide whether the installation protects people, and none of them shows in a photo.
- **How:** minimum list:
  1. Actual cross-section of each circuit vs. its PIA (ELEC-REV-11).
  2. Tightness (torque) of terminals, condition of the insulation behind the devices.
  3. Continuity of the PE to every socket outlet (*toma*) and exposed conductive part (ELEC-MED-3).
  4. Insulation resistance (ELEC-MED-4).
  5. Earthing resistance and condition of the earth rod (*jabalina*) ([earthing.md](earthing.md), ELEC-MED-5).
  6. Test each ID with a tester; confirm which circuits it covers (ELEC-MED-6).
  7. In three-phase, current per phase with a clamp meter (balance).
  8. Prospective Icc (from the utility) vs. breaking capacity of the devices.
  9. Actual order of the incoming devices (ID before or after the main switch) and what protects the ID upstream (ELEC-REV-27).
  10. If there is a generator set, UPS or inverter: changeover with no paralleling with the grid (ELEC-REV-25).
- **Verify:** that a written record remains with date, instrument and values; in workplaces, the protocol of Res. SRT 900/2015 (valid 12 months).
- **Don't:** close the report with "everything is fine" without this list.
- **Source:** AEA 90364-6 (Ed. 2025) and AEA 90364-7-770:2017, 770.19; Res. SRT 900/2015. See [testing-and-commissioning.md](testing-and-commissioning.md) (ELEC-MED-1 to 6).

## How to answer the person

### ELEC-REV-21: The report always has the same shape
- **Rule:** the agent returns the report with these sections, in this order, in plain language and citing rule IDs:
  ```text
  SUMMARY (2-4 lines)
    Which panel it is (single/three-phase, main/sub-panel), overall impression, the most serious issue.

  URGENT (do now; risk of electrocution or fire)
    - Finding [seen/deduced] → what to do meanwhile → rule.

  RECOMMENDED (fix soon, with a qualified electrician)
    - Finding → proposed fix → rule.

  IMPROVEMENTS (when work is done)
    - ...

  TO VERIFY IN PERSON (cannot be known from the photo)
    - Cross-section, tightness, earth, insulation, ID test, Icc...

  WHAT LOOKS GOOD
    - ...

  DEVICE READING (table)
    Row | Position | Brand | Poles | In and curve | Icn | Label | Remark
    (what cannot be read: "illegible")
  ```
  (The agent writes the report in the person's language, with these sections in this order.)
- **Why:** a fixed shape lets you compare two reviews of the same panel and lets the person know what to do first.
- **How:** if there is nothing urgent, say so explicitly ("I saw nothing urgent in the photo"). Include "what looks good" even if it is little: the person needs to know what not to touch. **By chat (Telegram):** a message has at most 4096 characters; if the report does not fit, split it into numbered messages (1/3, 2/3...) of no more than ~3500 characters, with SUMMARY and URGENT always in the first one. The reading table does not display well in chat: it goes as one line per row ("Row 1: ID 4P 63 A 30 mA | C40 4P TERMICA GRAL | ..."), in the last message, or is offered separately if the panel is large. IMPROVEMENTS can go as a couple of lines at the end of RECOMMENDED if it is short; the other sections are not omitted.
- **Verify:** every item has its certainty tag (ELEC-REV-2) and its rule.
- **Don't:** mix urgent with cosmetic; give prices; name the person or their address in the report.
- **Source:** this guide's criterion.

### ELEC-REV-22: Firm on what is urgent, honest on what is doubtful, and always refer
- **Rule:** for something urgent, the instruction is concrete (close the panel, don't use that circuit, switch off upstream if it is safe, knowing that the main switch only cuts what is downstream of it (ELEC-REV-9, ELEC-REV-27), call a qualified electrician). For the fix, recommend a professional or installer qualified in the jurisdiction; the agent does not give instructions for live work and does not guide a non-electrician to rebuild the panel.
- **Why:** the person may not be in the trade. What they can safely do on their own is little: not open anything further, not reset something that tripped with a burning smell, call, and press the ID test button **only if the panel has an inner cover (dead front, *contratapa*) or if they can reach the button without bringing their hand near terminals or bars**. Warn them first that the test cuts everything fed from that ID (with a single ID, the whole house: fridge, gate, pump) and that, if it does not reset or trips again, they should not insist and should call. If the panel is open, the electrician does the test on the visit.
- **How:** if the person is an electrician or installer, technical details of the fix can be given, always for dead work and referring to [panels.md](panels.md) and [site-safety.md](site-safety.md). If the installation has to pass a DCI (installation conformity declaration) or certificate (meter change, power increase), warn that many findings in this checklist will make it fail (see ELEC-NOR-10).
- **Verify:** that the report contains no steps that involve touching live parts.
- **Don't:** downplay ("eso no pasa nada", "that's nothing") or dramatize ("se va a prender fuego", "it's going to catch fire"); say "certifico" ("I certify").
- **Source:** Res. SRT 3068/2014; ELEC-SEG-2, ELEC-NOR-8.

## Common cases to recognize

### ELEC-REV-23: Old panels: fuses, knife switches, wood and cloth-covered cables
- **Rule:** recognize the old panel and say what is urgent. **Urgent:** fuses "reinforced" with wire or with a larger fuse, knife switches with exposed copper, terminals on the front of a wood or marble board with no cover, scorched wood, visibly cracked cloth or rubber insulation. **Important:** plug fuses (*tapón*) as circuit protection, no RCD, no PE, a single cable color. In every case the recommendation is to **replace the panel** (ELEC-TAB-26), not "add an RCD (*disyuntor*) in front of it".
- **Why:** a fuse reinforced with wire never blows (the cable burns first); the knife switch and front terminals leave live copper within reach of the hand; rubber and cloth crack with years and heat; wood carbonizes. Also, an old circuit with low insulation trips a new ID as soon as it is installed.
- **How:** recognize them in a photo:
  | What you see | What it is | Severity |
  |---|---|---|
  | Porcelain cylinders with a thread and a colored window at the tip | Plug fuse (Diazed type) | Important; urgent if there is wire or a plug larger than the original |
  | Porcelain base with a wire across it or a cable "puente" (jumper) | Wire fuse (*tabaquera*) or reinforced fuse | Urgent |
  | Lever with copper blades that go into jaws, exposed | Knife switch (*llave a cuchilla*) | Urgent if copper is visible with the cover open |
  | Wood, marble or slate board with screws and terminals on the front | Panel from the 50s-70s | Urgent if terminals are accessible; important in any case |
  | Cables with cloth braid, or rigid cracked black rubber, all one color | Old wiring with no PE | Urgent if visibly cracked; important if not |
  What to tell the owner: not to replace fuses with wire or with a larger one, not to replace one that keeps blowing, not to touch the panel, and to ask a qualified electrician for a replacement quote. The utility's fuses (NH or plug fuses in the meter pillar (*pilar*) or in the meter cabinet) are not touched (ELEC-PRO-20).
- **Verify:** in person, before replacing: insulation resistance of each circuit (ELEC-MED-4), presence of PE and condition of the earthing; if the wiring is cloth or rubber, it is replaced, not measured and left.
- **Don't:** put an ID in front of a panel with reinforced fuses; "straighten" a knife switch or remove a plug fuse live; say "it has worked for 50 years, it's fine".
- **Source:** [panels.md](panels.md) ELEC-TAB-26 and [troubleshooting-common-cases.md](troubleshooting-common-cases.md) ELEC-DIA-17 (old installations); [protection.md](protection.md) ELEC-PRO-20 (fuses); for new Edenor and Edesur supplies, the DCI prohibits fuses as circuit protection in the main panel (Res. ENRE, now ENReGE, 225/2011, section II point 3.9; ELEC-NOR-10). **Not verified in a primary source:** an express prohibition in the current AEA on plug fuses or rubber wiring in **existing** installations (the regulation applies to new installations and alterations; ELEC-DIA-17 did not find it either). The severity is this guide's criterion.

### ELEC-REV-24: Aluminum and copper-aluminum joints inside the panel
- **Rule:** aluminum conductors inside the panel, or direct copper-aluminum joints (twisted, taped or in a terminal not suitable for aluminum), are **important** findings; **urgent** if there are signs of heat (ELEC-REV-9). The aluminum of the utility's service drop reaches the meter pillar or the meter and is joined to copper with a bimetallic connector.
- **Why:** aluminum forms an oxide that conducts poorly and "flows" under the screw pressure, so the terminal loosens by itself; with moisture, the copper-aluminum pair corrodes. The result is a terminal that heats up without anything tripping.
- **How:** in the photo, aluminum looks like a gray or matte silver conductor at the stripped end (careful: tinned copper is also silver; and "CCA" cable, copper-clad aluminum, looks copper on the outside and silver when cut: see ELEC-FAB-7 in manufacturers-and-materials.md). If in doubt, it goes to "verify in person". The correct practice: copper throughout the indoor installation; if a length of aluminum remains, a bimetallic connector or a terminal marked suitable for Al/Cu, per the manufacturer (ELEC-CON-22).
- **Verify:** in person and dead: material of each conductor, type of joint, terminal marking, terminal condition (discoloration); under load, thermography.
- **Don't:** join copper and aluminum twisted together or in a shared terminal block; put aluminum in a PIA terminal that does not accept it; state "it's aluminum" only from the color in the photo.
- **Source:** [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-22 (Cu-Al only with bimetallic connectors); current-ratings-and-devices.md ELEC-AMP-7 (utility aluminum service drops); ELEC-DIA-17. **Not verified in a primary source:** the current AEA clause on aluminum conductors in the indoor installation of dwellings, and which PIA terminals accept aluminum (depends on each manufacturer).

### ELEC-REV-25: Generator set or inverter connected to the panel without a changeover switch
- **Rule:** if a generator set, a whole-house UPS or an inverter (solar, hybrid, with batteries) feeds the panel, it must come in through a **changeover switch that prevents connecting it to the grid at the same time**: a 3-position changeover switch (RED - 0 - GRUPO, grid - 0 - generator) that cuts phase and neutral in single-phase, or an automatic transfer switch with mechanical and electrical interlock; or, if it is an inverter that exports to the grid, a certified grid-tie inverter with anti-islanding protection and the user-generator (*usuario-generador*) registration. A generator plugged into a socket outlet (cable with two male plugs) or connected to the panel without a changeover switch is **urgent**. It is common since power outages became frequent.
- **Why:** without a changeover switch, the generator's voltage flows back through the meter to the street transformer (backfeed) and can electrocute the utility worker working on the line believing it is dead. Inside the house, if the generator comes in downstream of the main switch, some circuits **stay live with the main switch open**. When the grid comes back, the generator burns out.
- **How:** in the photo, look for a labeled changeover switch (RED/GRUPO, I-0-II), two interlocked contactors, an inverter or charger next to the panel, cables entering the panel at an odd place, a "dos fuentes" ("two sources") sign. Always ask: "¿tienen grupo electrógeno, UPS o paneles solares? ¿Cómo lo conectan cuando se corta la luz?" ("do you have a generator, UPS or solar panels? How do you connect it when the power goes out?"). If the answer is "lo enchufo en un toma" ("I plug it into a socket") or "lo conectamos directo al tablero" ("we connect it straight to the panel"), it is urgent: they must not use it that way until an electrician installs the changeover switch.
- **Verify:** in person, by an electrician: dead, that there is no continuity between the grid input and the generator input in any position of the changeover switch; with the generator running and the grid disconnected, absence of voltage on the grid side; that the ID works on the generator (generator neutral referenced to earth, ELEC-ESP-26); grid-tie inverter with anti-islanding certificate (IEC 62116).
- **Don't:** advise "enchufalo en un toma y bajá la general" ("plug it into a socket and switch off the main"); accept a changeover switch that cuts only the phase; consider a panel with two sources to be dead.
- **Source:** [special-installations.md](special-installations.md) ELEC-ESP-25 (changeover with no paralleling; AEA 90364-5-55 Ed. 2006, clause 551, text not verified), ELEC-ESP-26 (generator neutral and earth), ELEC-ESP-27 (UPS), ELEC-ESP-20 and ELEC-ESP-21 (user-generator under Ley 27.424 and Dec. 986/2018; inverters with IEC 62116); [panels.md](panels.md) ELEC-TAB-25 (interlocked changeover and two-sources sign). **Not verified in a primary source:** the exact text of AEA clause 551; the no-paralleling changeover criterion is taken from IEC 60364-5-55, 551.6, per ELEC-ESP-25.
### ELEC-REV-26: Other devices in the panel: recognize them before giving an opinion
- **Rule:** not everything on the DIN rail is an MCB (*térmica*). Identify each device and check what belongs to its function; if you don't recognize it in the photo, mark it "no identificado" ("not identified").
- **Why:** mistaking an isolator (*interruptor manual*) for an MCB, or a voltage protector (*protector de tensión*) for an SPD (*DPS*), leads to saying there is a protection that does not exist.
- **How:**
  | Device | How to recognize it | What to check |
  |---|---|---|
  | Combined MCB-RCD (*combinado térmica-diferencial*, RCBO, IEC 61009-1) | A single device with curve and In (C16) **and** IΔn (30 mA) and a T button | In single-phase, protection on both poles (ELEC-TAB-9); type AC/A; breaking capacity |
  | Isolator or switch-disconnector (*interruptor manual* or *seccionador*) | Lever with no curve and no Icn box; says "interruptor" or "seccionador", or I-0 | **Does not protect**: does not count as an automatic main switch (ELEC-REV-13) |
  | Voltage protector (over/undervoltage relay) | Module with display or LEDs, label "protector de tensión", settings for min/max V and delay | It is not an SPD or an ID; downstream of the incoming devices; acts through a contactor or through its own contact depending on the manufacturer (ELEC-PRO-19, ELEC-TAB-25) |
  | Contactor | Module with terminals A1-A2 (coil) and 1-2 / 3-4; sometimes hums | PIA upstream; if it drives a motor, a motor protection circuit breaker (*guardamotor*) or thermal overload relay set to the nameplate In; loud hum = check it |
  | Motor protection circuit breaker (*guardamotor*) | Setting knob in A, start and stop buttons | Setting ≈ motor nameplate current (pump, gate) (ELEC-ESP-14) |
  | Staircase timer (*automático de escalera*, *minutero*) | Module with a minutes knob and an "auto/permanente" selector | In a building it belongs in common services, not in an apartment (ELEC-TAB-20) |
  | Impulse relay (*telerruptor*) | Module with a lever or manual button, controlled by push buttons | Its PIA upstream; that the load does not exceed what the front says |
  | Time switch or timer | Dial with segments, or digital display with programs | That the load does not exceed the contact rating; if it does, a contactor |
  | Tank or pump controller (*automático de tanque*) | Level relay with terminals for electrodes or a float switch | Floats and electrodes in MBTS (ELEC-ESP-16); pump protection |
  | SPD | Green/red window, conductor to the earth bar | ELEC-REV-18 |
- **Verify:** in person: manufacturer's data sheet for each doubtful device, settings (motor protection circuit breaker, voltage protector, staircase timer) and that each one has its protection upstream.
- **Don't:** count an isolator as the "general" (main switch); say "it has lightning protection" because you see a voltage protector; touch settings based on the photo.
- **Source:** IEC 61009-1 (RCBO); [protection.md](protection.md) ELEC-PRO-19 and [panels.md](panels.md) ELEC-TAB-9, ELEC-TAB-20, ELEC-TAB-25; [special-installations.md](special-installations.md) ELEC-ESP-14 and ELEC-ESP-16. Product standards cited from general knowledge, **not verified in a primary source** in this review: IEC 60947-4-1 (contactors and motor starters, including motor protection circuit breakers), IEC 60669-2-2 (impulse relays) and IEC 60669-2-3 (staircase timers).

### ELEC-REV-27: Order of the incoming devices: which goes first, the main switch or the ID
- **Rule:** find out the actual order of the incoming devices, because it decides what the main switch cuts and what protects the ID. The usual arrangement in the main panel is **automatic main circuit breaker → ID → PIA**. If an ID is **before** the main switch, or if there are **two instantaneous 30 mA IDs in series**, it is a finding to verify (important if confirmed).
- **Why:**
  - If the ID is before the main switch, the main switch **does not make it dead** (nor its terminals), and its short-circuit backup (the SCPD its Inc was tested with) is whatever is **upstream of the ID**: the main panel's protection or the service drop fuses, not the main switch next to it.
  - Against overload, the ID is covered if its In ≥ the protection in series (upstream or, if everything that passes through the ID also passes through the main switch, the main switch) or ≥ the sum of those downstream (ELEC-REV-6, ELEC-PRO-10).
  - Two instantaneous 30 mA IDs in series (one in the TP and another in the sub-panel (*seccional*), or two in the same panel) have no selectivity (discrimination): they trip together or the upstream one trips, and a fault in one socket outlet cuts everything. The upstream one must be a selective "S" type of up to 300 mA (ELEC-PRO-12).
- **How:** the position on the rail **does not prove** the electrical order; it is only known by following the cables, which are almost never visible in a photo. Mark it "no verificable desde la foto" ("not verifiable from the photo") unless the cable from one device to the other is visible. Ask whether there is another panel next to the meter or the meter pillar (*pilar*) and what it contains.
- **Verify:** in person, by an electrician: dead, follow the incoming wiring; with an instrument and the procedure of ELEC-SEG-5, open the main switch and check whether the ID and each outgoing circuit become dead; ask the manufacturer for the coordination table ID-upstream protection.
- **Don't:** state that the main switch "cuts everything" because it is labeled that way; add a second instantaneous 30 mA ID upstream "just in case".
- **Source:** AEA 90364-7-770:2017, 770.16.5.3 (TP incoming device: automatic circuit breaker), 770.15.2.2.5 (In of the ID and its short-circuit protection) and 770.14.3.2 b) (upstream ID up to 300 mA, selective recommended), to be checked against Ed. 2026; IEC 61008-1 (Inc with stated SCPD), summarized; [protection.md](protection.md) ELEC-PRO-10 and ELEC-PRO-12; [panels.md](panels.md) ELEC-TAB-9, ELEC-TAB-10.

### ELEC-REV-28: Building: say which panel you are looking at and which standard applies to it
- **Rule:** in a building (this guide's case: PB + 4 floors, single-phase units) there are three different panels. Before giving an opinion, identify which one is in the photo, because the expected contents, the standard and who may work on it change.
  | Panel | Where it is | How to recognize it in the photo | Standard |
  |---|---|---|---|
  | Unit's TP | In the shared meter cabinet or meter room on PB, ≤ 2 m from the meter, in its compartment | Several meters next to it; per unit, a 2P PIA (sometimes with a 300 mA "S" ID), labeled with the unit ("2.º B") | 771 (the unit's); cabinet per the utility and AEA 95150 Ed. 2007 (ELEC-EDI-6, ELEC-TAB-20) |
  | Apartment's TSG | Inside the unit, near the entrance | 2P incoming device, one or more 30 mA IDs, 2P PIAs labeled by room; single-phase | 771 Ed. 2006 + 701 for the bathroom circuits |
  | Common services panel | PB, machine room or roof terrace, with its own meter | Usually three-phase (4P devices); labels "palier" (landing), "escalera" (stairs), "bomba" (pump), "ascensor" (elevator), "portero" (door intercom); staircase timers, contactors, pump controllers | 772 Ed. 2019 (+ 791 if there is an elevator) (ELEC-EDI-12) |
  The sub-main (feeder) that goes up the riser (*montante*) from the TP to the TSG complies with the unit's standard and also with the 772 (772.1.1, per [buildings.md](buildings.md)).
- **Why:** an apartment (*departamento*) in a building is **not** a "vivienda unifamiliar" (single-family house): it is designed under the **771**, although some apply the 770 relying on its clause 770.4.1.3; confirm with the jurisdiction (ELEC-CIR-1, ELEC-NOR-3). Common services have their own requirements (772) and are managed by the owners' association (*consorcio*), not by a neighbor.
- **How:** ask: (1) "¿El tablero está adentro del departamento, en PB al lado de los medidores, o en una sala de máquinas o terraza?" ("Is the panel inside the apartment, on PB next to the meters, or in a machine room or on the roof terrace?"); (2) "¿Cuántos medidores hay al lado?" ("How many meters are next to it?"); (3) "¿Qué dicen los rótulos?" ("What do the labels say?"); (4) "¿Los aparatos son de 2 o de 4 palancas unidas?" ("Do the devices have 2 or 4 levers joined together?"). If it is the common services panel, the report goes to the owners' association's management. In the shared meter cabinet, the utility's compartments are sealed and are not opened (ELEC-EDI-5).
- **Verify:** in person, that each switch in the shared meter cabinet is labeled with the correct unit (open one at a time and check at that unit's TSG, ELEC-TAB-20).
- **Don't:** judge a common services panel with the criteria for an apartment; recommend that a neighbor work on the common panel; open sealed compartments.
- **Source:** [regulations-and-permits.md](regulations-and-permits.md) ELEC-NOR-3 (AEA section by use; AEA catalog consulted 2026-11-15); [grades-and-circuits.md](grades-and-circuits.md) ELEC-CIR-1 (apartments under 771:2006); [buildings.md](buildings.md) ELEC-EDI-5, ELEC-EDI-6, ELEC-EDI-12 (AEA 772 Ed. 2019, 772.1.1; AEA 770:2017, 770.16.1 c) and 770.16.3.1); [panels.md](panels.md) ELEC-TAB-20; AEA 95150 Ed. 2007 (LV supply and metering) for the meter cabinet. **Not verified in a primary source:** the text of the 772 on the contents of the common services panel (paid standard).

### ELEC-REV-29: Air conditioner fed from a socket-outlet circuit
- **Rule:** each air conditioner (*aire*) over about 2250 frigories goes on its **own circuit** (a single-load supply circuit or a TUE with a single unit), with a two-pole C curve PIA chosen from the unit's nameplate and with In ≤ Iz of the cable. A split unit plugged into a general socket-outlet circuit (TUG), or hung off the lighting circuit, is **important**.
- **Why:** each socket outlet on a TUG accepts loads of up to 10 A, and in the demand schedule the whole circuit counts only 2200 VA (a statistical value, not a cap: the TUG's MCB is 16 or 20 A). An AC running for hours, plus whatever else is plugged into the same line, takes the circuit close to its MCB and overheats plugs and terminals. If it trips and someone "upsizes the MCB", the cable is left unprotected (ELEC-REV-11).
- **How:** look in the photo for a PIA labeled "AA", "AIRE", "SPLIT". If the house has ACs and there is no circuit for them, ask where they are plugged in. Reference: unit up to ~11 A nameplate → 2.5 mm² and PIA C16; more current → 4 mm² and PIA C20 (ELEC-ESP-11). Example of why they don't go on a TUG: two splits of 5.5 A nameplate each plus a 2000 W electric kettle (2000 W / 220 V = 9.1 A) on the same circuit: 5.5 + 5.5 + 9.1 = **20.1 A**, more than the 16 A of a PIA C16 on 2.5 mm². The agent does these calculations with `gateway electricidad` (current and coordination).
- **Verify:** in person: unit nameplate, cable cross-section, In ≤ Iz; on inverter units, type A ID (ELEC-ESP-2); cable between units longer than 3 m treated as installation (ELEC-ESP-11).
- **Don't:** plug the split in through a power strip (*zapatilla*); upsize the TUG's MCB "because it trips with the AC".
- **Source:** [special-installations.md](special-installations.md) ELEC-ESP-10 and ELEC-ESP-11 (AEA 90364-7-770:2017, 770.1, definition of equipment: cable between units is part of the equipment up to 3 m and a single slave unit; tables 770.12.I and 770.15.IV), ELEC-ESP-2; [grades-and-circuits.md](grades-and-circuits.md) ELEC-CIR-5 (TUG 2200 VA, TUE 3300 VA per circuit; circuit types of the 771, table 771.7.I). The 2250 frigories threshold is a practical criterion, **not** an AEA figure (per ELEC-ESP-11).

## Worked example: real panel sent by photo

Reference photo: panel of a house, with the door open (example file
`photo_2026-11-15_04-35-27.jpg`, not published). Whether it is the **main panel or a sub-panel cannot be known from the photo**:
ask whether there is another panel next to the meter or the meter pillar (it changes what protects upstream, ELEC-REV-27).
What follows respects ELEC-REV-2: **seen** (*visto*), **deduced** (*deducido*) or **illegible** (*ilegible*).

### What you see

**Enclosure and surroundings (seen):** painted beige frame and orange back plate, looking like a metal enclosure
(deduced: the photo does not confirm whether it is metal or whether the door is earthed). Four rails with devices;
in the photo **there is no inner cover (dead front, *contratapa*)**: all the terminal screws above and below the devices are visible, and two bare
brass terminal bars at the back. The right ends of the 3rd and 4th rows have free rail (spare space
available). A lot of surplus cable in loops along the sides and the top, with no wiring duct. A wide blue tape
over a bundle on the right side. A cut cable with a red/orange tip loose near the right end
of the bottom rail (it can't be seen whether it is live).

**Devices (seen): all Sica brand, "Limit" line on the PIAs where it can be read.**

| Row | Pos. | Device | Poles | In / curve | Handwritten label | Remark |
|---|---|---|---|---|---|---|
| 1 | 1 | RCD (*interruptor diferencial*) | 4 | 63 A | — | See data below |
| 1 | 2 | PIA | 4 | C40 | "TERMICA GRAL" (main MCB) | |
| 1 | 3 | PIA | 4 | C15 (could be C25) | doubtful: possibly "BOMBA AA PB" (or "BOMBA AG. PB") (ground-floor pump) | Deduced: maybe a pump (three-phase motor); don't state it is an AC. A motor without neutral needs 3 poles; the pump has its own protection (ELEC-ESP-14) |
| 1 | 4 | PIA | 2 | C10 | "ILUM PLAY" (playroom lighting; probable reading) | |
| 1 | 5 | PIA | 2 | C15 | "T SUITE" (suite sockets) | |
| 1 | 6 | PIA | 2 | C10 | "ILUM DORM..." (bedroom lighting; partial) | |
| 1 | 7 | PIA | 2 | C15 | illegible ("T D..."?) | |
| 2 | 1 | PIA | 2 | C10 | "ILUM SUITE" (suite lighting) | |
| 2 | 2 | PIA | 2 | C15 | "T PLAY" (playroom sockets) | |
| 2 | 3 | PIA | 2 | C10 | "ILUM COCINA" (kitchen lighting) | |
| 2 | 4 | PIA | 2 | C15 | "T COCINA" (kitchen sockets) | |
| 2 | 5 | PIA | 2 | C10 | covered with black and yellow tape | Different model (darker blue lever); a box reading "3000" is visible |
| 2 | 6 | PIA | 2 | C15 | illegible | |
| 2 | 7 | PIA | 2 | C10 | "ILUM ESTAR" (living room lighting) | |
| 2 | 8 | PIA | 2 | C15 | "T ESTAR" (living room sockets; faint) | |
| 2 | 9 | PIA | 2 | C10 | "ILUM SE..." ("SERV"?, service) | |
| 2 | 10 | PIA | 2 | C10 (could be C16) | in red, "T. BAÑO SUITE" (suite bathroom sockets; probable reading) | Illegible additions in red; bathroom sockets at 10 A: verify what it feeds |
| 3 | 1 | PIA | 2 | C15 | "T LAVADERO" (laundry sockets) | Lever at O-OFF |
| 3 | 2 | PIA | 2 | illegible (covered) | "ILUM S. MUS." (music room lighting) + paper stuck on ("NO USAR"?, "do not use", doubtful) | Different model, gray/brown levers; at O-OFF |
| 3 | 3 | PIA | 2 | C15 | "T. SALA MUS..." (music room sockets) | At O-OFF |
| 3 | 4 | PIA | 2 | C10 | "ILUM GALER..." (gallery lighting) | At I-ON |
| 3 | 5 | PIA | 2 | C10 | "ILUM GARAGE" (garage lighting) | At O-OFF |
| 3 | 6 | PIA | 2 | illegible (covered by paper) | paper: "ILUM EX..." (outdoor lighting?), rest illegible | |
| 3 | 7 | PIA | 2 | C10 | no label | Different front design (printed I-ON/O-OFF legend); at O-OFF |
| 3 | 8 | PIA | 2 | C15 | no label | Same as the previous one; at O-OFF |
| 3 | 9 | PIA | 2 | C10 | "L. EXT CONTR" (outdoor lights, rear) | At O-OFF |
| 4 | 1 | PIA | 2 | C10 | "L EXT FREN..."? (outdoor lights, front) + paper stuck on (illegible) | At O-OFF (apparently) |
| 4 | 2 | PIA | 2 | C15 | "PORTON" (gate) | At I-ON |
| 4 | 3 | PIA | 2 | C10 | "PILETA" (pool) | At I-ON |

Totals (seen): **1 four-pole ID, 2 four-pole PIAs and 26 two-pole PIAs** (27 outgoing circuits counting the 4P
in position 3). Legible currents: almost all "ILUM" (lighting) at 10 A and almost all "T" (socket outlets) at 15 A, 40 A on
the main switch. Exceptions: "T. BAÑO SUITE" at C10 (could be C16), "PILETA" and "L. EXT CONTR" at C10, "PORTON" at C15.

**RCD data (seen, small print; doubtful items in parentheses):** "Interruptor diferencial 4 polos" (4-pole RCD);
In 63 A; IΔn 0.03 A (30 mA); 240/415 V~; (Im = IΔm = 630 A, probable reading, consistent with the standard's minimum
10 × 63 A); (Inc 3000 A, probable reading); SCPD fuse 63 A; IEC 61008-2-1; legend "Prueba mensualmente" ("test monthly") next to
the test button. **Type (AC or A): illegible** (there is a small symbol that can't be made out). Lever in the closed
position (deduced from the position).

**Breaking capacity of the PIAs:** on at least one (row 2, pos. 5) a box reading "3000" (3 kA) is visible; on the others the
box exists but the number **can't be read**.

**Wiring (seen):** cable jumpers between the top terminals of the PIAs; **no busbar comb (*peine*) is visible**. In row 2, the
phase jumpers are **red in the left half** (roughly positions 1 to 5) and **black or dark brown on the
right** (6 to 10); in rows 3 and 4 they are **brown**; the neutral jumpers are light blue or blue (greenish light blue
in row 4). Colors present: red, black and brown (phases), light blue and blue (neutrals), **several plain green** and
some green-yellow, which reach the lower left bar (deduced: it is the earth bar; on the right there is
another bar with light blue and green conductors, and it is not clearly identified which one is the neutral bar). A **red conductor**
(phase color) **also reaches** that left bar, next to a green-yellow one; nearby there is a red object that could
be a splice cap (doubtful). Ferrules can't be distinguished at this resolution. No darkened insulation
is noticeable, but the photo is not enough to rule it out.

**Not visible:** SPD, single-line diagram, electrical hazard symbol (it may be on the door, outside the photo), the
assembler's details.

### Reading: it is a three-phase panel (deduced)

**Deduced on good grounds:** the supply is **three-phase** (3 × 380/220 V + N): 4-pole RCD, 4-pole main switch
and one 4-pole circuit; the 220 V circuits are two-pole and should be distributed across the three
phases. **Deduced from color, not measured:** the brown phase seems to feed rows 3 and 4 (about 12 circuits, with
laundry, outdoors, gate and pool), the red and the black about 5 each in row 2, and the 4 two-pole devices of
row 1 don't show which phase they take. Brown would carry more circuits than the other two: **measure current
per phase with a clamp meter** (ELEC-REV-20). With the C40 main switch, what the incoming device lets through is S = √3 × 380 V × 40 A ≈
**26.3 kVA** (≈ 23.7 kW with cos φ = 0.9; ELEC-REV-4); the power that can be used is the contracted power. It is a
dwelling with a 40 A incoming device, so it falls within the scope of the **770** (≤ 63 A, if in addition the prospective Icc is ≤ 10 kA);
if the contracted current or the incoming device exceeded 63 A, or if it were not a dwelling, the 771 would apply. The
number of circuits does not define which AEA section (770 or 771) applies.

**Not verifiable from the photo:** the electrical order between the ID (position 1) and the "TERMICA GRAL" (position 2), and whether
the other 4P PIA and all the two-pole ones hang off the C40. If the ID is before the main switch, switching off the main switch does **not**
make the ID or its terminals dead, and its short-circuit backup is whatever is upstream (ELEC-REV-27).

### What is right

- Uniform brand and line in almost all devices (a well-known Argentine manufacturer); compatible spare parts and busbar combs
  easy to get (seen).
- All 220 V circuits with a **two-pole PIA** (they cut phase and neutral); no single-pole device visible (seen;
  ELEC-REV-7).
- There is a **4P PIA labeled "TERMICA GRAL"** (seen; ELEC-REV-13); it remains to confirm that it cuts everything, including the ID
  (ELEC-REV-27). There is a **30 mA ID** (seen; ELEC-REV-10).
- Small currents and generally consistent: almost all lights at 10 A and almost all socket outlets at 15 A,
  compatible with 1.5 and 2.5 mm² respectively **if** those are the cross-sections (to verify; ELEC-REV-11).
  Exception to review: "T. BAÑO SUITE" at C10.
- ID In (63 A) ≥ main switch (40 A): if everything that passes through the ID also passes through the C40, it meets the
  series device criterion; if not, compare with the upstream protection or with the sum of those downstream
  (to verify; ELEC-REV-6, ELEC-REV-27).
- Almost all circuits are labeled and there is free rail for spare space (ELEC-REV-19).

### What is wrong or doubtful

1. **No inner cover in the photo:** terminals, jumpers and brass bars within reach with the door open. If the panel
   is used like this, it is **urgent** (ELEC-REV-8). The inner cover may exist and have been removed for the photo: ask.
2. **A single RCD for about 27 circuits**, including "PILETA", "PORTON" and outdoor lights: trips from
   accumulated leakage, the whole house dark at each trip and the temptation to bypass (jumper) it. **Important** (ELEC-REV-10).
   Also, it can't be known from the photo whether **all** circuits pass through that ID (ELEC-REV-20).
3. **Pool:** the "PILETA" circuit (C10) has its own requirements (AEA 90364-7-702, zones, MBTS, equipotential bonding,
   30 mA ID); with a single shared ID, any leakage from the pump cuts the whole house. **Important**; see
   [special-installations.md](special-installations.md).
4. **Cable jumpers** in rows of 9 and 10 devices, without a busbar comb (the 770 allows them only up to 3 outgoing circuits):
   many terminals with two conductors and possible hot spots. **Important** (ELEC-REV-15).
5. **Plain green** on several conductors: a color prohibited today; it is not known for certain what each one is. **Important**
   (ELEC-REV-14).
6. **Devices of other models** interspersed (row 2 pos. 5, row 3 pos. 2, 7 and 8): later replacements; verify
   standard, marking and breaking capacity of each one. **Important** (ELEC-REV-17).
7. **Breaking capacity:** the only legible one is 3 kA. In a three-phase supply close to the meter the prospective Icc may be higher:
   ask the utility for it and compare. **To verify** (ELEC-REV-5, ELEC-REV-17).
8. **ID coordination:** the ID declares its Inc (3000 A, probable reading) with a 63 A fuse as backup. Its
   actual backup is the protection that is **upstream of the ID**: if the ID is before the C40, it is the main
   panel's or the service drop's, not the C40. Find out what is upstream and ask the manufacturer for the
   coordination table. **To verify** (ELEC-REV-6, ELEC-REV-27).
9. **ID type illegible:** if it is AC and there is a lot of electronics (gate, pump with a variable-speed drive, inverter ACs), consider
   type A. **To verify**.
10. **No SPD visible:** depends on whether the service drop is overhead, on the keraunic level and on whether there is a lightning rod.
    **Case by case** (ELEC-REV-18).
11. **Circuits at O-OFF and "no usar" notes(?):** several PIAs in rows 3 and 4 appear open. If they are circuits
    out of service, they should be disconnected in the panel and labeled as spare. **Improvement / to verify**
    (ELEC-REV-19).
12. **Handwritten labels**, several illegible, one covered with tape and two with paper stuck on; no visible single-line diagram.
    **Improvement** (ELEC-REV-19).
13. **Untidiness:** cable loops, blue tape over a bundle (it may hide a splice), loose cable with a cut tip.
    **To verify in person**; a splice inside the panel or a loose live cable would be important.
14. **Brass bars with no cover or identification** (N/PE): **important** for live parts if it is the neutral bar;
    confirm which is which (ELEC-REV-8, ELEC-REV-16).
15. **Red conductor (phase color) on the lower left bar**, together with green and green-yellow ones (seen):
    it is not known what it is (a red used as PE or as neutral, or a phase taken to a bar). It is more serious than the
    plain greens because it misleads the next person who works on the panel. **Important:** verify in person and
    dead what it connects, and re-identify or replace it (ELEC-REV-14, ELEC-REV-16).
16. **Unbalanced phases (deduced from color):** brown seems to feed about 12 circuits and the other two about 5
    each. **To verify** with a clamp meter (ELEC-REV-4, ELEC-REV-20).
17. **"T. BAÑO SUITE" at C10:** bathroom socket outlets at 10 A are unusual (the usual rating for socket outlets is 15 or 16 A); it may be a
    mislabeled lighting circuit or a changed MCB. **To verify** what it feeds and with what cross-section (ELEC-REV-19).

### What a licensed electrician (*matriculado*) would recommend (prioritized)

1. **Now:** a cut-out inner cover with blanking plates and a cover on the bars; meanwhile, panel closed and no one
   opens it except to operate it. The electrician tests the ID button on the visit: in this panel with no inner cover,
   the owner would have to bring their hand near exposed terminals (ELEC-REV-22), and the test leaves the whole house without power
   (gate, pool, fridge), because there is a single ID.
2. **Soon (a single job, dead work, by a qualified electrician):**
   - Split the RCD protection: for example, one 30 mA 4P or 2P ID per group, distributing lighting and
     socket outlets across different IDs and with **pool, gate and outdoors on their own IDs**; if the general 4P ID is kept, it
     has to become a selective type with a higher IΔn (300 mA "S") so that there is selectivity (ELEC-TAB-19).
   - Replace the jumpers with **busbar combs** per group; one neutral terminal block per ID; earth bar
     identified and separate.
   - Change the plain greens to green-yellow (or identify them after verifying they are PE); clarify and
     re-identify the red on the lower bar; remove or label the circuits no longer in use; take splices out of the panel.
   - Rebalance the phases according to the clamp meter measurement (ELEC-TAB-24).
   - Check the devices of other models and, if they lack marking or sufficient breaking capacity, replace them.
   - Assess an SPD per ELEC-REV-18.
3. **To verify in person:** cross-sections against each PIA, torque, earthing resistance (Ω), PE continuity, insulation, test
   of the ID with an instrument, which circuits it covers, phase balance with a clamp meter, prospective Icc.
4. **Later:** printed labels, single-line diagram on the door, dressing of the wiring.

### What the single-phase equivalent would look like

For a single-phase apartment (for example, in the 4-floor building this guide uses as its case; see
[buildings.md](buildings.md), ELEC-TAB-20 and ELEC-REV-28), with fewer circuits. An apartment is designed under the
**771** (plus the 701 for the bathroom), not the 770; the sub-main that goes up the riser also complies with the 772.

```text
TP in the collective meter cabinet (PB), next to the meter (≤ 2 m)
  PIA 2P C32 or C40 (protects the sub-main; Icn ≥ prospective Icc)
  + ID 2P 300 mA "S" if the sub-main is not Class II or there are exposed conductive parts along the run (ELEC-PRO-12)
  └─ sub-main 2 × calculated cross-section + PE  → goes up the riser to the apartment
Apartment TSG (Class II enclosure, with inner cover and ≥ 20 % spare)
  Switch-disconnector 2P 40 A (incoming)
  SPD (if applicable, ELEC-REV-18); voltage protector recommended in buildings (ELEC-PRO-19)
  ├─ ID1 2P 40 A 30 mA  ── 2P busbar comb ── PIA 2P C10 IUG1 | PIA 2P C16 TUG2 kitchen
  ├─ ID2 2P 40 A 30 mA  ── 2P busbar comb ── PIA 2P C16 TUG1 | PIA 2P C10 IUG2
  ├─ ID3 2P 40 A 30 mA (type A if the unit is an inverter)
  │     ── PIA 2P C16 dedicated air-conditioning circuit (2.5 mm², unit up to ~11 A nameplate; ELEC-REV-29)
  ├─ N terminal block for each ID; identified PE terminal block
  └─ blanking covers in the spare space
```

Differences from the example: everything **2-pole** (incoming device, ID and PIA); a single phase color; there is no phase balance
to look after inside the apartment (the building looks after it by distributing the units across phases, ELEC-EDI-10); with
40 A the incoming device lets through S = 220 V × 40 A = **8.8 kVA**, against ≈ 26.3 kVA for the three-phase one. The power that
can be used is limited by the power **contracted** with the utility, not only by the C40. A 30 mA ID in the TP and other 30 mA ones
in the TSG, all instantaneous, would have no selectivity (ELEC-REV-27): upstream goes the 300 mA "S" or nothing, depending on the line.
Illustrative values: the cross-sections and protections come from the calculation (`gateway electricidad`) and from
[grades-and-circuits.md](grades-and-circuits.md).
If a 4-pole ID is reused in a single-phase supply, connect the poles the manufacturer indicates so that the
test button works (ELEC-REV-7); a 2P is preferable.

### Report the agent would return (summarized)

```text
SUMMARY
  Three-phase panel (deduced from the 4-pole devices); main or sub-panel, cannot be told from the photo.
  26 circuits at 220 V + 1 four-pole, all under a single 30 mA ID. The most serious: in the photo there is no
  inner cover (terminals and busbars exposed).

URGENT
  - No inner cover: live parts accessible with the door open [seen]. Keep the panel closed,
    nobody opens it except to operate it, and fit an inner cover and blanking covers. (ELEC-REV-8)

RECOMMENDED
  - Split the circuits across several IDs; pool, gate and outdoor areas separate. (ELEC-REV-10)
  - Busbar combs instead of cable jumpers. (ELEC-REV-15)
  - Replace the green conductors with green-yellow; find out what the red one reaching the earth
    bar is [seen]. (ELEC-REV-14, ELEC-REV-16)
  - Check the 4 devices of a different model. (ELEC-REV-17)
  - Assess an SPD depending on the service entrance. (ELEC-REV-18)
  - The electrician tests the ID button when they come (with the panel open it is better that you
    don't do it; it cuts the whole house). (ELEC-REV-6, ELEC-REV-22)

IMPROVEMENTS
  - Printed labels, single-line diagram, remove circuits no longer used, tidy the wiring. (ELEC-REV-19)

TO VERIFY IN PERSON
  - Cross-sections vs MCBs, terminal tightness, earthing, insulation, ID test and which circuits it covers,
    order ID / main switch and what protects the ID upstream, current per phase (the brown one looks more
    loaded [deduced]), prospective Icc vs 3 kA, ID type (AC/A), what "T. BAÑO SUITE" on C10 feeds, what
    position 3 of row 1 is (pump?), what is under the blue tape. (ELEC-REV-20, ELEC-REV-27)

WHAT LOOKS GOOD
  - All two-pole, there is a 4P labeled as main, a single brand, almost all lights on 10 A and the socket
    outlets on 15 A, almost everything labeled, there is spare space.
```

## What this guide does not replace
- A review by photo **gives guidance**; it is not an inspection or a certificate. The diagnosis, the design of the
  fix and the signature (DCI, certificate, SRT 900/2015 protocol) are done by a professional or qualified installer
  with competence in the jurisdiction (see [regulations-and-permits.md](regulations-and-permits.md)).
- The **utility** decides its own matters (service drop, meter, power, the Icc it reports) and the **municipality** or the regulatory
  body decides the approval.
- The current AEA Reglamentación (including Ed. 2026 of the 770, already published, whose clauses must be checked against
  those of Ed. 2017 cited here) and each device's manufacturer data sheet prevail over this guide.
- No step in this guide authorizes live work or an untrained person opening a panel.
