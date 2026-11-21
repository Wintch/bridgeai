---
title: Apartment buildings (condominium buildings, propiedad horizontal) - supply, risers and common services
scope: electrical installation of a multi-dwelling residential building in Argentina (ground floor + 3 to 10 floors typical) - utility feasibility and service connection, 770/771 scope per unit, meter room/cabinet, lines to each unit through the riser, phase balancing and broken neutral, common services (elevator, pumps, landings, emergency lighting, door entry, gate, garages/EV, fire, generator), building earthing and lightning protection, power factor of the owners' association, construction stages, existing buildings and maintenance
when_to_use: designing, supervising or reviewing the common electrical part of a building; deciding whether a unit goes under 770 or 771; locating the meter room; sizing the lines that go up the riser; distributing units among phases; diagnosing overvoltages caused by a broken neutral; building the common services panel; planning the stages of the electrical work; renewing risers or increasing power in an existing building; drawing up the maintenance plan for the owners' association
related: [README.md, regulations-and-permits.md, grades-and-circuits.md, conductors-and-conduits.md, protection.md, earthing.md, panels.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md]
as_of: 2026-11-15
sources:
  - AEA 90364-7-770 Viviendas (dwellings; single-family up to 63 A; BA2 and BD1), 2017 edition (text consulted, published by the Municipalidad de Junín); the 2026 edition appears in the AEA catalog with the same scope (≤ 63 A, ≤ 10 kA), but its text was not consulted
  - AEA 90364-7-772 Instalaciones de espacios comunes y servicios generales (common areas and common services installations), 2019 edition (in force per the AEA catalog as of 2026-11)
  - AEA 90364-7-771 Viviendas, oficinas y locales unitarios (dwellings, offices and single shops), 2006 edition
  - AEA 95150 Suministro y medición en baja tensión (low-voltage supply and metering), 2007 edition
  - ENRE, Reglamento de Suministro (supply regulation, Edenor/Edesur), text updated by Res. ENRE 524/2017 and 525/2017 ("edición 2022" PDF on argentina.gob.ar)
  - ENRE Res. 225/2011, Reglamento para la conexión de nuevos suministros (rules for connecting new supplies, 2022 edition text), and Res. ENRE 269/2012 (DCI)
  - Res. ENRE 628/2024 (power factor in condominium buildings, B.O. 2024-09-11), via summaries in the specialized press; Decreto 452/2025 (ENReGE)
  - AEA 90364-7-791-T1 Ascensores (elevators), 2018; AEA 90364-7-791-T2 Escaleras mecánicas, ascensores vehiculares y similares (escalators, vehicle elevators and similar), 2020; AEA 90364-7-722 Vehículos eléctricos (electric vehicles), 2024 (official AEA extract)
  - AEA 95501-3 (IRAM 2281-3) Puesta a tierra hasta 1 kV (earthing up to 1 kV), 2024; AEA 92305 / IRAM 2184 Protección contra rayos (lightning protection), 2015
  - IRAM-AADL J 2027 (emergency lighting), only through technical publications
  - Código de Edificación CABA (Buenos Aires City building code, Ley 6100 amended by Ley 6438), RT-030809-020309-01 v4 (2023)
  - Edenor service connection diagrams published in Ingeniería Eléctrica No. 319-327 (2017)
---
# Apartment buildings

This guide covers the **common** electrical part of a condominium building (*propiedad horizontal*): from the utility
(distribution company, *distribuidora*) network up to each unit's panel, plus everything the owners' association (*consorcio*)
feeds (common services). What is inside each apartment (*depto*) (electrification grade, circuits, the apartment's panel) is in
[grades-and-circuits.md](grades-and-circuits.md), [panels.md](panels.md) and [reviewing-a-panel.md](reviewing-a-panel.md).

Each rule has an ID (ELEC-EDI-n) so the agent, a review or a site report can cite it
("no cumple ELEC-EDI-7": "does not comply with" that rule). For calculations (current, voltage drop, cross-section, demand,
coordination, earthing) the agent uses the offline calculator `gateway electricidad ...` instead of calculating from memory; the
worked examples here help to understand and check the result.

**Safety first:** in a meter room, even if you switch off all the MCBs (*térmicas*), the following **stay live**: the utility
service box (*caja de toma*), the utility's fuses, the busbars, each meter (input and output), the main line and the input
terminals of each incoming switch. If a unit's main panel is inside the apartment (arrangement 2, see "Typical structure"),
the line going up the riser (*montante*) also stays live. If there is a generator, UPS or solar panels, there can be voltage
even if the utility has cut the supply. What is upstream of the incoming switch can only be made dead by a utility
disconnection: do not open it or touch it (see ELEC-EDI-5 and [site-safety.md](site-safety.md)).

## Which standard governs each section

| Section | Who decides / which standard | Note |
|---|---|---|
| Network, service connection, utility service box, main fuses, meters | Utility (Reglamento de Suministro + its installation standards) and AEA 95150 (2007 ed.) | The user supplies and installs boxes/cabinet as the utility indicates |
| From the meter output terminal to the first isolation point | AEA 95150 + 770/771 (the main line is calculated with 770/771) | AEA 770 (2017) 770.4.1.1 |
| Installation of each dwelling (apartment) | AEA 90364-7-771 (this guide's criterion); 770 only if the authority accepts it in writing and the incoming switch is ≤ 63 A, the prospective short-circuit current (Icc) at the origin is ≤ 10 kA and the use is BA2/BD1 | 770.1 a-c, 770.4.2 f, 770.16.5.3; see ELEC-EDI-26 |
| Shops and offices in the building | AEA 90364-7-771 (770 is only for dwellings) | See ELEC-EDI-26 |
| Common services and common areas; also the sub-mains that run up the riser | AEA 90364-7-772 (2019 ed.) | 772.1.1: applies from the input of the common services main panel, and sub-mains in riser columns must also comply with 772 |
| If due to occupancy or evacuation the building is "pública concurrencia" (public assembly) | AEA 90364-7-718 (2008 ed.) | Stricter cables, wiring systems and emergency lighting |
| Passenger elevators | AEA 90364-7-791-T1 (2018) + municipal code/registry | |
| Car lifts / vehicle elevators, escalators, ramps | AEA 90364-7-791-T2 (2020) | Garages with car lifts |
| Electric vehicle charging | AEA 90364-7-722 (2024) | See ELEC-EDI-18 |
| Earthing up to 1 kV | AEA 95501-3 / IRAM 2281-3 (2024) + 770/771 | See ELEC-EDI-20 |
| Lightning protection | AEA 92305 / IRAM 2184 (2015) | Risk assessment, see ELEC-EDI-21 |
| Building, means of egress, mandatory elevator, meter rooms | Municipal building code (Código de Edificación) | CABA: Ley 6100 amended by Ley 6438 + technical regulations |

**Why AEA is mandatory in the Edenor/Edesur area:** the ENRE Reglamento de Suministro requires the user to install the
protective devices at the metering output and in the main panel in accordance with the AEA "Reglamentación para la
ejecución de instalaciones eléctricas en inmuebles" (regulations for electrical installations in buildings) (art. 2 inc. c),
and to maintain the installation downstream of the first isolation point in compliance with that regulation or local
standards (art. 2 inc. d). In the rest of the country the obligation comes from provincial or municipal law or regulation
(see [regulations-and-permits.md](regulations-and-permits.md)).

**National regulator for the Edenor/Edesur area:** Decreto 452/2025 (B.O. 2025-07-07) created the Ente Nacional
Regulador del Gas y la Electricidad (ENReGE, national gas and electricity regulator), which according to the official ENRE
website takes over its functions progressively from May 2026. The ENRE resolutions cited here remain the reference text
until they are replaced; confirm in the Boletín Oficial (details in ELEC-NOR-18). In the rest of the country the provincial
regulator and the local utility or cooperative govern (EPEC, EPE, EDEA, etc.).

## Quick reference

| Situation | Rules |
|---|---|
| Starting the project / requesting the service | ELEC-EDI-1, ELEC-EDI-2, ELEC-EDI-3, ELEC-EDI-26 |
| Does the unit go under 770 or 771? Ground-floor shops | ELEC-EDI-26 |
| Locating and building the meter room or cabinet | ELEC-EDI-4, ELEC-EDI-5, ELEC-EDI-6 |
| Riser and lines to each apartment | ELEC-EDI-7, ELEC-EDI-8, ELEC-EDI-9 |
| Phase balancing, overvoltages, "se quemaron aparatos en varios deptos" (appliances burned out in several apartments) | ELEC-EDI-10, ELEC-EDI-11 |
| Common services panel | ELEC-EDI-12 |
| Elevator, pumps, landings, emergency lighting | ELEC-EDI-13 to ELEC-EDI-16 |
| Door entry system, gate, antennas, fiber, garages, EV chargers | ELEC-EDI-17, ELEC-EDI-18 |
| Fire, pressurization, firefighter shutdown | ELEC-EDI-19 |
| Generator, UPS, solar panels on common services | ELEC-EDI-27 |
| Earthing, equipotential bonding, lightning protection | ELEC-EDI-20, ELEC-EDI-21 |
| Power factor penalty for the owners' association (AMBA) | ELEC-EDI-22 |
| Construction stages, inspections, connection, completion | ELEC-EDI-23, ELEC-EDI-24, ELEC-EDI-25 |
| Existing building: old risers, more power, air conditioning | ELEC-EDI-28 |
| Periodic maintenance by the owners' association | ELEC-EDI-29 |

## Typical structure

```
Utility LV network (3x380/220 V)
   │
[Utility service box / service and protection module]  ← NH fuses, busbars, neutral (sealed: utility)
   │
[Collective meter cabinet]  ── common services meter (three-phase) ── TP common services ── TS elevator (machine room)
   │                                                                                        ├─ TS pumps
   │                                                                                        ├─ TS landings + emergency
   │                                                                                        └─ TS garages / gate / EV
   ├─ apt 1A meter ── TP 1A (≤ 2 m) ── sub-main up the riser ── TSG in apt 1A
   ├─ apt 1B meter ── TP 1B ...
   └─ ...
Main earthing bar ── earth rod(s) / foundation electrode ── equipotential bonding (water, structure, SPCR)
```

Two arrangements are common and you should know which one you have, because it changes which cable is the "main line":

1. **Each unit's main panel in the meter room** (no more than 2 m from the meter). What goes up the riser is a
   **sub-main circuit** to the apartment's general sub-panel (TSG). This is the arrangement the regulations require by
   default, and it lets you disconnect each apartment from the meter room.
2. **Main panel inside the apartment.** What goes up is the **main line**, which has no protection of its own and can
   only be disconnected with the utility's fuse. It is only allowed if the utility or the authority accepts it
   (exception to the 2 m rule) and the line must be double-insulated along its whole route.

---

## Supply and service connection

### ELEC-EDI-1: Request feasibility from the utility (*distribuidora*) in writing before closing the design
- **Rule:** before defining the meter room and the service connection conduit, submit the supply request in writing with
  the building's load estimate. The utility sets the space for meters, the conduit linking to the network, the cabinets
  and materials up to the first isolation point, and it must tell you the prospective short-circuit current at the
  supply point.
- **Why:** each utility has its own approved cabinets, heights and locations; if you build the niche before knowing them,
  it gets broken and rebuilt. The prospective Icc is needed to choose the breaking capacity of the breakers (see
  [protection.md](protection.md)) and it defines which regulation governs each unit: with more than **10 kA** at the
  origin, the unit no longer falls under 770 and is designed with 771 (ELEC-EDI-26). In a building with its own
  transformer substation or close to one, the Icc in the meter room can exceed that value.
- **How:** prepare the load estimate (units × demand + common services, see the example case); request by letter the
  feasibility, the prospective Icc and the installation standards in force for "suministro colectivo / medidores
  agrupados" (collective supply / grouped meters); keep the dated reply in the job folder.
- **Verify:** you have in writing: type of supply, approved location of service box and meters, cabinet model,
  prospective Icc (compare it with **10 kA**: if it exceeds it, ELEC-EDI-26), whether they require space for a
  transformer substation (ELEC-EDI-2).
- **Don't:** copy the cabinet from "the previous job" with another utility or from another year; installation standards
  change and the utility states them "en la oportunidad" (at the time).
- **Source:** AEA 90364-7-770 2017 ed., 770.4.3 (utility requirements) and 770.4.2 f (the installer requests the
  prospective Icc from the utility; if it exceeds 10 kA, 771 governs); ENRE Reglamento de Suministro (text Res. ENRE
  524/525-2017) art. 1 inc. g (the user installs the service box and metering boxes "según las normas de instalación
  vigentes en la oportunidad" (according to the installation standards in force at the time)); AEA 90364-7-772 2019 ed.,
  772.1 (service connections are governed by AEA 95150).

### ELEC-EDI-2: If total demand exceeds 60 kVA, reserve a room for a transformer substation
- **Rule:** in the Edenor/Edesur area, when the new supply (or the sum of the building's supplies) exceeds
  **60 kVA**, or when the existing network is not enough even with less power, the utility can require the owner to
  provide a suitable space for a transformer substation (CT, *centro de transformación*), under an agreement that sets
  conditions and compensation.
- **Why:** a building with 8-10 apartments plus common services is close to that number (see the example case); if the
  building is "all-electric" (no gas: induction cooktop, water heater or heat pump, AC in every room) it is well above
  it. If the CT request appears once the structure is built, there is nowhere to put it.
- **How:** add up the simultaneous demand with a margin for growth (air conditioning, EV chargers with diversity factor 1
  unless there is load management, ELEC-EDI-18). If there is no gas, calculate each apartment's DPMS (maximum simultaneous
  power demand) with the real electrical loads ([grades-and-circuits.md](grades-and-circuits.md)): it usually ends up in the
  range of 10 to 14 kVA or more, not 7 kVA. If you are close to 60 kVA, ask about it explicitly in the feasibility
  request and reserve the space on the ground floor with street access until the utility answers.
- **Verify:** written reply from the utility about the CT; if applicable, signed agreement and room shown on the drawings.
- **Don't:** "shrink" the load estimate to stay below the threshold; the power declaration is a sworn statement and an
  undersized building ends up with fuses that blow and cables that overheat.
- **Source:** ENRE Reglamento de Suministro (text Res. ENRE 524/525-2017, 2022 ed. PDF on argentina.gob.ar) art. 1
  inc. g "Centro de transformación y/o maniobra - toma primaria" (transformer and/or switching substation - primary
  supply) (60 kVA threshold) and art. 2 inc. a (sworn statement). The 10-14 kVA range for an apartment without gas is a
  guideline, not a standard value. Other provinces: check the local utility's regulation.

### ELEC-EDI-3: The building is supplied three-phase; units are usually single-phase
- **Rule:** the collective supply of a building is three-phase 3×380/220 V, 50 Hz. Each small-demand unit (T1 tariff)
  is normally connected single-phase 220 V between one phase and neutral; common services with motors (elevator, large
  pumps) are connected three-phase. A unit with high demand may require a three-phase supply: the utility decides.
- **Why:** three-phase lets you distribute the load and feed motors; each single-phase apartment is simpler and cheaper,
  but it forces you to balance the phases well (ELEC-EDI-10) and to guard against a broken neutral (ELEC-EDI-11).
- **How:** define for each unit whether it is single-phase or three-phase in the load estimate. As a reference, in
  Edenor's diagrams the T2 tariff (medium demand) is three-phase from 10 to 49 kW, with a three-phase meter and main
  panel no more than 2 m away. Ground-floor shops usually have their own meter, often three-phase, in the same
  collective cabinet or in a separate one depending on the utility (ELEC-EDI-26).
- **Verify:** the unit schedule shows the voltage, assigned phase and power of each meter.
- **Don't:** feed one unit from two meters, or mix part of an apartment with common services, except for the
  provided exception (central building equipment that enters a unit), always with a design.
- **Source:** AEA 90364-7-770 2017 ed., 770.4.1.3 (a single normal supply per dwelling; exception for installations of a
  dwelling "que forme parte de edificios" (that is part of buildings) fed from common services) and 770.4.2
  (220/380 V, 50 Hz ± 1 Hz); Edenor diagrams published in Ingeniería Eléctrica No. 327 (Dec 2017) for T2 from 10 to
  49 kW. **Not verified in a primary source:** the exact single-phase power limit each utility accepts; ask for it in
  the feasibility request.
### ELEC-EDI-26: Design each apartment with 771; use 770 only if the authority accepts it and the unit is within its scope
- **Rule:** this guide's criterion (the same as ELEC-CIR-1, ELEC-CON and ELEC-REV): each apartment (*depto*) is designed with
  **AEA 90364-7-771**. 770 is presented as a section for "viviendas unifamiliares" (single-family dwellings); although its text
  mentions dwellings that are part of buildings (770.4.1.3, 770.16.1) and some jurisdictions accept it for apartments, use it
  only if the enforcing authority accepts it in writing **and** the unit meets all of these at once: main panel incoming
  switch of **63 A** maximum, prospective short-circuit current (Icc) at the origin of **10 kA** maximum, and BA2 users / BD1
  evacuation. With more than 63 A, more than 10 kA, or if it is a shop or office, it is 771, no discussion.
- **Why:** 770 simplifies decisions based on those limits (for example, breaking capacity and the cross-section tables);
  applied outside its scope it can leave breakers with insufficient breaking capacity, or a shop with requirements that do
  not apply to it.
- **How:**
  1. With the Icc reported by the utility (distribution company, *distribuidora*) (ELEC-EDI-1) and each unit's demand, add a
     "standard" column to the unit schedule: 771 by default; 770 only with the authority's written acceptance.
  2. An ordinary single-phase T1 apartment with Icc ≤ 10 kA is the only case where 770 can be discussed; even then, where
     the two differ (mandatory 1 % on the sub-main, 1.5 mm² switch returns, 150 VA per IUG outlet point (*boca*)), 771 is
     stricter.
  3. Large "all-electric" apartments or those with a three-phase supply above 63 A, and all ground-floor shops and offices,
     go under 771. Common services go under 772 (ELEC-EDI-12).
  4. Each unit's calculations come from `gateway electricidad` with the correct standard selected.
- **Verify:** schedule with the reported Icc, incoming switch current and standard applied per unit; breaking capacity of
  each incoming switch ≥ Icc at that point ([protection.md](protection.md)).
- **Don't:** cite 770 for a shop or for a unit with 15 kA in the meter room; design an apartment with 770 without the
  authority's written acceptance; mix values from the two in the same unit.
- **Source:** AEA 90364-7-770 2017 ed., foreword (for loads above 63 A, Icc above 10 kA, BA3-BA5, BD2-BD4, offices or
  shops "se debe continuar aplicando la Sección 771" (Section 771 must continue to be applied)), 770.1 a-c (63 A, 10 kA, BA2
  and BD1), 770.4.2 f (Icc > 10 kA → 771), 770.16.5.3 (incoming switch above 63 A → 771), 770.4.1.3 and 770.16.1 (dwellings
  in buildings, collective cabinet). AEA catalog (consulted 2026-11-15): the 2026 ed. of 770 keeps the scope "hasta 63 A y
  Icc presunta hasta 10 kA (BA2 y BD1)" (up to 63 A and prospective Icc up to 10 kA). **Not verified in a primary source:**
  the full text of the 2026 ed. (changes in numbering or requirements); confirm it if your jurisdiction has already adopted it.

## Meter room and meter cabinet

### ELEC-EDI-4: The meter room or niche: common access, dry, lit, signposted and free of other services' pipes
- **Rule:** the meter room or cabinet is kept clean, dry, signposted, lit and free of obstacles, with access for utility
  staff without going through a private unit. Panels (distribution boards, *tableros*) go in a dry place, away from water,
  gas and sewage installations, with **0.9 m** clear in front and at least **200 lx**. The specific location (normally the
  ground floor, near the property line), the cabinet model and other conditions are set by the utility in the feasibility
  reply.
- **Why:** the utility has the right to access the meters and the user has the obligation to keep the room in good
  condition; water and gas near live busbars are the worst scenario.
- **How:**
  - Mandatory (Reglamento de Suministro and 770): room clean, dry, signposted, lit, unobstructed and accessible; panels in
    a dry place and away from water, gas and sewage; electrical hazard symbol on the front; 0.9 m clear in front; 200 lx at
    1 m above the floor on the front.
  - Whatever the utility requires: model and heights of the collective cabinet (ELEC-EDI-1), location on the ground floor
    or on the property line. In Edenor's diagrams, utility service boxes (*cajas de toma*), isolation and meter boxes are at
    least **30 cm** from the gas cabinet.
  - Recommended / good practice: self-contained emergency lighting (770 lists it as "recomendable" (recommended)),
    ventilation, a door with a lock that both the owners' association (*consorcio*) and the utility can open; do not place
    it under the escape stairs or inside the pump room.
  - The specific requirements for rooms used exclusively for electrical equipment (access, clear height, ventilation,
    doors) are in AEA 772, clause 772.24 (and 772.24.2 if there is a generator); annex C has examples of a switchroom with
    recommended distances (figures 772.C.3 and 772.C.4).
  - In CABA the Código de Edificación (building code) has a section on rooms for utility installations and meters
    (3.3.1.6.2): review it with the architect.
- **Verify:** walk-through with the utility or with its standard in hand; no other services' pipes crossing; lighting (and
  emergency lighting, if installed) working; access without going through a private unit.
- **Don't:** use the meter room as a storeroom or storage locker; block access with bicycles or furniture.
- **Source:** ENRE Reglamento de Suministro art. 2 inc. d (meter cabinets/rooms clean, dry, signposted, lit and free of
  obstacles) and inc. f (access for utility staff); AEA 90364-7-770 2017 ed., 770.16.2.1 (dry place, away from water, gas
  and sewage; electrical hazard symbol), 770.16.2.2 (0.9 m) and 770.16.2.3 (200 lx; emergency lighting "recomendable");
  AEA 90364-7-772 2019 ed., 772.24 and figures 772.C.3/C.4; Edenor diagrams in Ingeniería Eléctrica No. 327 (2017), note on
  distance to gas. **Not verified in a primary source:** exact dimensions, ventilation and heights of 772.24 (paid standard)
  and the text of art. 3.3.1.6.2 of the Código de Edificación CABA.

### ELEC-EDI-5: The utility service box (*caja de toma*) and metering module belong to the utility: don't open them or bypass them
- **Rule:** the collective cabinet typically consists of a service and protection module (copper busbars, NH fuse bases,
  neutral bar, terminal blocks), a metering module and a user protection module. Use a cabinet approved by your utility.
  Everything upstream of the user's first isolation point that carries a seal is operated only by the utility.
- **Why:** that part has no upstream protection that you can switch off: a short circuit there is an arc at the full power
  of the network. Also, tampering with the utility's installations or its seals is prohibited.
- **How:** the installer brings their cables to the terminals the utility indicates and leaves **50 cm of cable** spare in
  each box (criterion of the Edenor diagrams). If work is needed upstream of the first isolation point, the utility or its
  authorized staff does it (connection to service or meter terminals, sealing). The installer only works on their own part,
  from the output they are told, with the disconnection confirmed by the utility, locked out/tagged out (LOTO) and with
  absence of voltage verified with a two-pole voltage tester (see [site-safety.md](site-safety.md), ELEC-SEG-3 to
  ELEC-SEG-5).
- **Verify:** seals intact; terminal cover in place; each output labeled with the unit it feeds.
- **Don't:** remove an NH fuse "to cut off an apartment"; bypass a meter; open the inner cover (dead front, *contratapa*)
  while live. **Danger of death.**
- **Source:** ENRE Reglamento de Suministro art. 2 inc. e (the user may not tamper with, repair, remove or modify the
  utility's installations between the connection and the first isolation point) and art. 4 inc. c (seals); Ingeniería
  Eléctrica, "Gabinetes de medición colectiva" (collective metering cabinets) (Conextube, May 2026: service/metering/
  protection modules, Edenor and Edesur approval); Edenor diagrams in Ingeniería Eléctrica No. 327 (2017).

### ELEC-EDI-6: Each unit's main panel (TP, *tablero principal*) goes no more than 2 m from the meter, and it is Class II
- **Rule:** the main panel (the one with the unit's incoming switch) is installed no more than **2 m** from the collective
  meter cabinet. Its enclosure is Class II insulated, standardized and certified, assembled maintaining double insulation;
  the main line and its conduit also comply with double insulation. Outdoors, degree of protection no lower than **IP54**.
- **Why:** the main line (meter → main panel) has no overload protection of its own; the shorter and better insulated it
  is, the lower the risk. In a building, putting all units' incoming switches in the meter room lets you disconnect any
  apartment without entering it (useful in emergencies and for the owners' association's electrician).
- **How:** in the collective cabinet, the compartments that house the main switches act as main panels. Use an incoming
  switch that breaks phase and neutral, with breaking capacity matching the reported Icc (see [protection.md](protection.md)
  and [panels.md](panels.md)).
- **Verify:** measure the real distance; the enclosure has the Class II mark (double square) and a certificate; the line
  from the meter to the switch does not touch metal parts.
- **Don't:** leave the meter on the ground floor and the first switch on the 4th floor without a written agreement from the
  utility (it is the exception, not the rule); use a metal enclosure without maintaining double insulation.
- **Source:** AEA 90364-7-770 2017 ed., 770.16.1 (definition of collective cabinet and compartments as main panels) and
  770.16.3.1 (2 m, Class II, IP54; exception by agreement between designer, user and utility or authority); Edenor T2
  diagrams in Ingeniería Eléctrica No. 327 (2017): panel no more than 2 m away, IP41 minimum indoors. Check against the
  2026 edition of 770 if your jurisdiction has already adopted it.

## Risers and lines to each unit

### ELEC-EDI-7: One conduit per line, the PE with its phases, accessible junction boxes and fire sealing between floors
- **Rule:** each main line runs in its own conduit. Sub-main circuits with single-core cable (IRAM NM 247-3 or IRAM 62267)
  also run in separate conduits; up to three sub-mains in the same conduit are allowed only if they are sheathed cables
  (IRAM 2178-1 or IRAM 62266) and from the same meter. All conductors of a circuit, including the PE, run in the same
  wiring system. Conduit between the main panel and the first sub-panel (including the riser (*montante*) conduit):
  **absolute minimum diameter R19 / R20 (3/4")**, recommended **R25 (1")**; the real diameter comes from the fill: the
  cables, with their insulation, may not occupy more than **35 %** of the conduit's internal cross-section.
- **Why:** one conduit per unit lets you rewire one apartment without touching the others and prevents a fault in one cable
  from damaging the neighbor's line. The PE next to its phases keeps the fault loop impedance low. With the cross-sections
  usually needed in a riser (ELEC-EDI-8), R19 is too small.
- **How:**
  - Fill for phase + neutral + PE of equal cross-section in medium-weight steel conduit, according to the table in
    [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-12: 6 mm² → RS 22 (RL 19 in light-weight);
    10 mm² → RS 25; 16 mm² → RS 32. Example: 3 cables of 16 mm² with the maximum outer diameter AEA uses
    (8.8 mm, tables 770.10.VII to IX) occupy 3 × π/4 × 8.8² ≈ 182 mm²; at 35 % an internal cross-section of
    182 / 0.35 ≈ 521 mm² is needed, that is, an internal diameter of about 25.8 mm: R25 is not enough, R32 is needed (the
    table in [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-12 gives RS 32 / RP 32 / CL 32). The
    standard's fill tables govern; the 35 % is only for non-tabulated cases and with AEA's maximum diameter, not the
    catalog one; details in
    [conductors-and-conduits.md](conductors-and-conduits.md).
  - Riser in its own shaft or duct, accessible from common areas on each floor, separated from gas, water and drains.
  - In vertical conduits, cables are supported with devices in accessible boxes at intervals of **15 m maximum**, without
    damaging the insulation; no splices inside the conduits.
  - A junction box on each floor (where the line branches to the apartment) with a screwed cover.
  - Seal each slab penetration with material whose fire resistance is no lower than that of the floor slab.
  - Label each line **at both ends** (meter room and apartment) with the unit it feeds.
- **Verify:** on site, before energizing: each junction box with one set of cables per conduit, PE present, legible labels,
  seals in place; continuity of each unit's PE to the earthing bar (see
  [testing-and-commissioning.md](testing-and-commissioning.md)). **In an occupied building, opening a riser junction box is
  working near live parts:** the other apartments' lines are still energized. Visual inspection only, with PPE and without
  touching conductors. To handle or adjust anything, first switch off and lock out the incoming switches of **all** the
  units that pass through that box and verify absence of voltage with a two-pole voltage tester. If what runs up the riser
  is a main line (arrangement 2), the disconnection has to be done by the utility (ELEC-EDI-5,
  [site-safety.md](site-safety.md)).
- **Don't:** put the lines of several units in the same cable tray or conduit with single-core cable; use a common
  "building" PE that runs from box to box with splices; leave the shaft open between floors (smoke chimney); buy R19
  conduit for a 10 or 16 mm² line because "es el mínimo" (it's the minimum).
- **Source:** AEA 90364-7-770 2017 ed., 770.10.3.8.2 a-c (grouping), 770.7.1 p (R19/R20, recommended R25, includes risers;
  refers to the internal area of 770.10.3.3.4), 770.10.3.3.4 e) and tables 770.10.VII to IX (tabulated fill),
  770.10.3.8.4 (35 % of the internal cross-section in non-tabulated cases; minimum internal diameter 15 mm for main or
  sub-main circuits; same as ELEC-CON-12) and
  770.10.3.8.1 (support every 15 m, no joints in conduits); AEA 90364-7-772 2019 ed., 772.1.1 (sub-mains in risers also
  comply with 772) and 772.14 (wiring systems). The cross-section → conduit equivalence is a guideline (typical catalog
  outer diameters). **Not verified in a primary source:** separation distances to other installations and the sealing
  requirement according to the final text of 772 (they appear in the 2017 discussion draft: 0.5 m separation and sealing
  with resistance equal to that of the floor slab).

### ELEC-EDI-8: Each line's cross-section comes from current, voltage drop and short circuit, not from habit
- **Rule:** size each line to each unit by (1) current-carrying capacity with its protection, (2) voltage drop and
  (3) short-circuit thermal stress. The voltage drop between the main panel output and any point of use must not exceed
  **3 %** in lighting and socket outlet circuits, and **5 %** in steady state (15 % at starting) in circuits feeding only
  motors; the sub-main does not exceed **1 %**: mandatory in 771 (with which each apartment is designed, ELEC-EDI-26; it
  leaves 2 % for the final circuit leaving the apartment's panel) and recommended in 770. Minimum cross-sections (770 and
  771): main line **4 mm²**, sub-main circuits **2.5 mm²**, protective conductor **2.5 mm²**; in a riser, the calculation
  almost always gives considerably more.
- **Why:** in a building, the top-floor apartment can be 20-40 m of cable from the meter: with the "usual" 6 mm² the riser's
  drop eats more than half of the 3 % margin and the apartment is left with low voltage when the AC starts.
- **How:** 770 uses `ΔU = k · I · L · (R cos φ + X sin φ)`, with k = 2 for single-phase, L in km, R = effective resistance
  of the conductor at operating temperature in Ω/km and X the reactance in Ω/km. For small cross-sections X matters little
  and can be neglected.
  Example: 4th-floor apartment, 20 m sub-main (L = 0.020 km) from the main panel (on the ground floor) to the apartment's
  panel, I = 7000 VA / 220 V = 31.8 A, cos φ = 0.9. R at 70 °C = maximum R at 20 °C (IEC 60228, class 2) × (1 + 0.00393 × 50):
  6 mm² → 3.08 × 1.197 = 3.69 Ω/km; 10 mm² → 1.83 × 1.197 = 2.19 Ω/km; 16 mm² → 1.15 × 1.197 = 1.38 Ω/km.
  - 6 mm²: ΔU = 2 · 31.8 · 0.020 · 3.69 · 0.9 = 4.22 V → **1.92 %** (does not meet the sub-main's 1 %).
  - 10 mm²: 2.51 V → **1.14 %** (does not meet the 1 %).
  - 16 mm²: 1.58 V → **0.72 %** (complies).
  Cross-check with the 770 voltage drop table in V/(A·km) (see table 770.15.IV, cos φ 0.8, includes reactance):
  it gives 1.88 %, 1.10 % and 0.69 %; the calculator (class 5 cable) gives 2.06 %, 1.19 % and 0.75 %. The conclusion is
  the same: with 771 it is **16 mm²**. Only if the authority accepted 770 for that apartment (1 % recommended) could 10 mm²
  remain, with short final circuits and a total ≤ 3 %. Use `gateway electricidad drop --line submain` and
  `gateway electricidad size --circuit submain` for the real calculation (for this case it proposes 16 mm²).
- **Verify:** calculation report with the drop per section (sub-main + final circuit) ≤ 3 %; voltage measurement in the
  farthest apartment under load (see [testing-and-commissioning.md](testing-and-commissioning.md)); conduit matching the
  chosen cross-section (ELEC-EDI-7).
- **Don't:** add up only the final circuit's drops and forget the riser; choose the cross-section only from the current
  table.
- **Source:** AEA 90364-7-770 2017 ed., 770.4.1.1 (main line: AEA 95150 + calculation per 770), table 770.11.I
  (minimum cross-sections: main line 4 mm², sub-mains 2.5 mm², PE 2.5 mm²), 770.15.6 (3 %, 5 %/15 %,
  1 % recommendation for sub-mains; formula in item a) and table 770.15.IV); AEA 90364-7-771 Ed. 2006, 771.13 b) and
  its note (1 % mandatory on the sub-main, 2 % on the final circuit from the sub-panel), according to
  [conductors-and-conduits.md](conductors-and-conduits.md) ELEC-CON-9; IEC 60228 (maximum resistances at 20 °C).
  **Not verified in a primary source:** the equivalent minimums in 771/95150 and in the 770 2026 ed. See also
  [conductors-and-conduits.md](conductors-and-conduits.md).
### ELEC-EDI-9: In common areas and risers (*montantes*), prefer low-smoke, halogen-free (LS0H) cables
- **Rule:** in risers (*montantes*), landings (*palieres*), garages and common rooms, use flame-retardant cables and,
  preferably, low emission of opaque smoke and zero halogens (single-core IRAM 62267, sheathed IRAM 62266). If the building
  qualifies as public assembly ("pública concurrencia", BD classification by number of people or evacuation), wiring
  systems, cables and emergency installations must comply with AEA 718, which requires them.
- **Why:** in a fire, the black smoke and acid gases from PVC in the stairwell kill more than the fire itself; the riser
  connects all floors.
- **How:** specify IRAM 62267 / 62266 in the specifications for everything common; where they run in a cable tray, use
  sheathed cable. Annex A of AEA 772 covers the behavior of cables in a fire.
- **Verify:** the marking printed on the cable sheath states the standard (62267 or 62266) and the certification mark.
- **Don't:** use flexible cord (*tipo taller*, cord for appliances) in fixed installations, or uncertified cable.
- **Source:** AEA 90364-7-772 2019 ed., 772.1 (referral to 718 if there is public assembly) and annex A (informative);
  AEA 90364-7-770 2017 ed., current table calculated for IRAM 62266 (low smoke, zero halogen).
  **Not verified in a primary source:** that 772 makes LS0H mandatory in every residential building; take it as a
  recommendation unless 718 or a municipal requirement applies.

## Phase balancing and broken neutral

### ELEC-EDI-10: Distribute the single-phase units among the three phases and document it
- **Rule:** assign each single-phase unit to a phase so that demand is as balanced as possible between L1, L2 and L3, and
  record the phase in the schedule, in the cabinet and in each apartment's (*depto*) panel (distribution board, *tablero*).
  In a collective cabinet, each unit's phase is taken in the utility's (distribution company, *distribuidora*) module: the
  assignment is agreed with the utility.
- **Why:** with unbalanced phases, one phase is overloaded (and its fuses blow) while the others have spare capacity, more
  current flows in the neutral and, if the neutral breaks, the voltage in the units becomes much more unbalanced
  (ELEC-EDI-11).
- **How:** with similar units, rotate the assignment (1A-L1, 1B-L2, 2A-L3, 2B-L1...). Single-phase common services loads
  (landings, door entry, emergency lighting) go on the least loaded phase. EV chargers and large shops are distributed
  among phases or fed three-phase. See the table in the example case.
- **Verify:** with the building occupied, measure with a clamp meter the current of each unit at the output of its
  incoming switch, on the user side, on the insulated cable and with the panel front in place, at peak hours, and add up
  per phase according to the schedule. If a unit has to be reassigned to another phase, always ask the utility: the phase
  is taken in its sealed module. The currents of the common service connection and the common neutral are measured by the
  utility.
- **Don't:** connect a whole floor, or all apartments with central air, to the same phase; open the service module to
  measure or to "move" an apartment to another phase.
- **Source:** AEA 90364-7-770 2017 ed., 770.7.1 n (in three-phase installations keep the system as balanced as
  possible); ENRE Reglamento de Suministro (supply regulation) art. 2 inc. e and art. 4 inc. c (utility installations and
  seals). **Not verified in a primary source:** a maximum regulatory unbalance percentage for buildings; use the designer's
  judgment.

### ELEC-EDI-11: Protect each unit against overvoltage from a broken neutral, and look after the neutral on the user side
- **Rule:** installing protection against permanent overvoltages and undervoltages in each single-phase unit is strongly
  recommended (AEA rates it "altamente recomendable" (highly recommended) and leaves it to the designer's judgment). The
  neutral is treated in two sections: (a) **upstream of the meters** (network, service connection, utility service box
  (*caja de toma*), neutral bars) it belongs to the utility and is not touched; (b) **on the user side** (meter output,
  incoming switches, risers, common services panels) the neutral has the same cross-section as the phase, is never switched
  on its own, and its connections are tightened to the manufacturer's torque, always with the power off.
- **Why:** if the common neutral breaks upstream of the units, loads on different phases end up in series between phases
  (380 V) and the voltage divides according to the load: the apartment with little load gets a voltage close to 380 V and
  its appliances burn out; the heavily loaded apartment is left with low voltage. The most frequent cause is the utility's
  network or service connection, not the building's installation.
  Simplified example (two loaded phases, resistive loads):
  - Apartment A on L1 with 500 W → R = 220² / 500 = 96.8 Ω. Apartment B on L2 with 4000 W → R = 220² / 4000 = 12.1 Ω.
  - With the neutral broken they are in series across 380 V: I = 380 / (96.8 + 12.1) = 3.49 A.
  - U_A = 3.49 · 96.8 = **338 V** (destructive overvoltage); U_B = 3.49 · 12.1 = **42 V**.
- **How:**
  - Protector, two options (details and thresholds in ELEC-PRO-19): (1) modular voltage protector (over/undervoltage relay)
    with its own switching relay, in series after the incoming switch, with a rated current **equal to or greater** than
    that of the incoming switch and timed automatic reset; (2) voltage relay acting on a shunt trip coil of the incoming
    switch: it disconnects, but **does not reset by itself** (manual reset, unless a reset motor is added), or one that
    controls a contactor.
  - Coordinated transient overvoltage protection (SPD, *DPS*) (see [protection.md](protection.md)); an SPD does not replace
    the voltage protector.
  - User section: neutral of the same cross-section as the phases (electronic and LED loads generate harmonics that add
    current in the neutral), lugs and terminals tightened to the manufacturer's torque with the incoming switch off and locked out.
    Thermography is done under load, by trained staff and with PPE, through viewing windows or with the method of
    ELEC-MED-23; if nobody can do it safely, switch off, lock out/tag out (LOTO) and retighten.
  - Utility section: if suspected (heating, smell, odd voltages in several apartments), file a complaint with the utility
    and switch off the incoming switches of the affected units, without opening anything sealed.
- **Verify:** test the protector with the manufacturer's test function and write the thresholds on the panel; in
  diagnosis, if several apartments on different phases report "luces que brillan de más" (lights too bright) and others
  "luces débiles" (dim lights), suspect the neutral: **don't measure it by opening live terminals**, notify the utility
  and switch off incoming switches (see ELEC-DIA-14 in
  [troubleshooting-common-cases.md](troubleshooting-common-cases.md)).
- **Don't:** use single-pole breakers or ones "con neutro no protegido" (with unprotected neutral) as incoming switch; put
  a fuse or an isolator in the neutral alone; trust that a transient SPD protects against a broken neutral (it does not);
  put a 40 A modular protector after a 63 A incoming switch; "tighten the neutral" in the utility service box.
- **Source:** AEA 90364-7-770 2017 ed., 770.13.1 b (protection against permanent overvoltages due to "interrupción del
  conductor neutro" (interruption of the neutral conductor) and against undervoltages: "altamente recomendables"),
  770.15.5 (at the designer's judgment) and 770.16.5.1 (incoming switches break the neutral; devices with unprotected
  neutral are not allowed); AEA 90364-7-771 2006 ed., 771.17 (mandatory and highly recommended measures) and 771.19.5 /
  771.19.6 (permanent overvoltages; undervoltages or zero voltage), according to the official index; ENRE Reglamento de
  Suministro art. 2 inc. e (utility installations). On neutral cross-section: AEA 90364 Part 5 (2006 ed.), chapter 52,
  equivalent to IEC 60364-5-52 cl. 524. **Not verified in a primary source:** the AEA text of that clause and the exact
  item of 771.17; the trip current of modular protectors comes from each manufacturer's catalog.

## Common services

### ELEC-EDI-12: Common services with their own meter, their own main panel and one sub-main per system
- **Rule:** the owners' association (*consorcio*) has its own meter (normally three-phase) and its common services main
  panel (TP-SG), from which sub-main circuits run to panels per system: elevator (in the machine room), pumps, landing and
  emergency lighting, garages/gate, and any others. Each elevator/goods lift and each pump system has its own dedicated
  circuit. RCDs (*disyuntores* / *diferenciales*) are coordinated so that a fault in one circuit does not leave the whole
  building in the dark.
- **Why:** a fault in the pump must not switch off the stairwell; the owners' association's electrician must be able to
  switch off one system without switching off the others.
- **How:**
  - Panel structure according to the diagrams in 772.7.3 (figure 772.7.A); minimum number of circuits in common areas
    according to table 772.8.I and minimum points according to 772.8.2.
  - Demand for common services and units according to 772.9 (tables 772.9.I, 772.9.II and 772.9.III); use
    `gateway electricidad demand`.
  - Upstream, if the line between panels needs residual current protection: selective RCD (type S, time-delayed) with a
    **higher** rated residual current, typically up to **300 mA** (that is, **less** sensitive), and 30 mA RCDs per group of
    final circuits downstream. Selectivity (discrimination) needs both things: upstream IΔn at least 3 times the
    downstream one, and time delay. 770 **recommends** (does not require) that the 300 mA ones be selective with the 30 mA
    ones; with IΔn ≤ 300 mA and Ra ≤ 40 Ω that section is considered protected against indirect contact. See ELEC-PRO-12.
  - Spare space in the panels (770 requires at least 20 % in 18 mm modules) and a socket outlet circuit for maintenance in
    each plant room.
  - Rooftop and machine room: service socket outlets and luminaires with an IP rating for outdoors; tank float switches
    with long wiring, preferably in SELV (MBTS) (ELEC-ESP-16). The caretaker's apartment is one more unit (with its own
    meter, or with sub-metering if the owners' association feeds it from common services), not a circuit hanging off the
    landings.
- **Verify:** up-to-date single-line diagram on the TP-SG door; labels on each output; test each RCD with its button and
  with an instrument; the upstream one has the "S" on the front and a higher IΔn than the downstream ones.
- **Don't:** hang the stairwell lighting on the same RCD as the pumps; feed common services from an apartment's meter;
  put a 30 mA (or more sensitive) RCD upstream "para más seguridad" (for extra safety): it trips first and switches
  everything off.
- **Source:** AEA 90364-7-772 2019 ed., 772.7.3, 772.8.I, 772.8.2, 772.9 (index and scope verified in the official extract
  published by AEA); AEA 90364-7-770 2017 ed., 770.14.3 b (ID with IΔn ≤ 300 mA between panels, "recomendándose"
  (recommending) that they be selective with the 30 mA ones, symbol S; with Ra ≤ 40 Ω, 24 V is not exceeded) and 770.16.4
  (20 % spare); factor of 3 between IΔn values: criterion from IEC 60364-5-53 and manufacturers' catalogs. **Not verified
  in a primary source:** the values of tables 772.8.I and 772.9.I-III (paid standard; the 2017 draft required at least 2
  lighting circuits, 1 socket outlet circuit, 1 per elevator and 1 per pump system).

### ELEC-EDI-13: Elevator: dedicated three-phase supply up to its panel in the machine room
- **Rule:** each elevator is fed with a dedicated three-phase sub-main circuit from the TP-SG to the elevator's motive
  power sub-panel in the machine room (or in the place defined by the manufacturer if it is machine-room-less), with a
  lockable isolating switch within the technician's reach. Car, shaft and machine room lighting, and service socket
  outlets, on circuits separate from motive power, so they do not go off when the motor is switched off.
- **Why:** the elevator technician works in the shaft and in the machine room with motive power off; they need light and
  must be able to lock out the disconnection. Variable speed drives (VVVF) generate leakage currents with a DC component
  that can blind or trip standard RCDs.
- **How:** ask the elevator manufacturer for power, starting current, recommended RCD type (type A, F or B depending on
  the drive) and cross-section; check the voltage drop at starting (5 % in steady state / 15 % at starting for motor
  circuits). The limit of the building's installation is the motive power and lighting sub-panel in the machine room
  (with a lockable switch); the control panel or controller (with the drive) and everything after it belongs to the
  elevator contractor. Coordinate with them the supply of auxiliaries that must keep working during an outage: car
  emergency lighting, alarm or intercom, and the automatic rescue device (it takes the car to the nearest floor and opens
  the doors) if installed. Car lifts or vehicle elevators: AEA 90364-7-791-T2. Register the elevator in the municipal
  maintenance registry (in CABA, Registro de Conservación de Elevadores (elevator maintenance registry)) with a licensed
  maintenance company.
- **Verify:** lockable isolation in the machine room; shaft and car lighting working with motive power off; car emergency
  lighting and alarm working with the mains off; PE of the elevator structure bonded to the earthing bar.
- **Don't:** feed the elevator from a socket outlet or share the circuit with pumps; work in the shaft without
  coordinating with the maintenance company; hang the car lighting on the same switch as motive power.
- **Source:** AEA 90364-7-791-T1 2018 ed. (passenger elevators) and 791-T2 2020 ed. (escalators, vehicle elevators and
  similar), existence verified in the AEA catalog; AEA 90364-7-772 2019 ed. (circuit per elevator); AEA 90364-7-770 2017
  ed., 770.15.6 (5 %/15 % motors); GCBA, "Declaración de elevadores" procedure (elevator declaration: every building with
  elevators must declare them in the Registro de Conservación de Elevadores). **Not verified in a primary source:** the
  details of 791-T1/T2 (isolation, shaft lighting, car emergency lighting and alarm, automatic rescue); they are common
  industry practices and from the European standard EN 81-20.

### ELEC-EDI-14: Water pumps: panel with motor protection circuit breaker (*guardamotor*), level control and dry-run protection
- **Rule:** each pump system (lift pump cistern → tank, booster pump) has its panel with a main switch, motor protection
  circuit breaker (*guardamotor*) (or MCB (*térmica*) + thermal overload relay) and contactor per pump, control by float
  switches or level sensors in the tank and cut-off at minimum level in the cistern, alternation if there is a standby
  pump, and an RCD.
- **Why:** a pump that runs dry burns out in minutes; one that does not stop when the tank is full overflows. The pump
  room is damp: it is where the RCD and earthing matter most.
- **How:** motor protection circuit breaker set to the motor's nameplate rated current; float switch contacts at safety
  extra-low voltage when the manufacturer allows it (ELEC-ESP-16); boxes and panel with an IP rating suitable for a damp
  environment and away from possible drips; motors bonded to the PE. Example of a pump room in AEA 772 figure 772.C.7.
- **Verify:** simulate full tank, empty tank and empty cistern and check that the pump starts and stops as it should; test
  the RCD; measure the motor current with a clamp meter against the nameplate.
- **Don't:** bypass the cistern float switch "porque cortaba" (because it kept cutting out); leave the panel on the floor
  of the room.
- **Source:** AEA 90364-7-772 2019 ed. (one circuit per pump system; figure 772.C.7 "sala de bombas elevadoras de agua"
  (water lift pump room)). **Not verified in a primary source:** motor protection circuit breaker, alternation and minimum
  level as a regulatory requirement; they are good design practice (see
  [special-installations.md](special-installations.md)).
### ELEC-EDI-15: Landings (*palieres*) and stairs: timed or sensor switching, never leaving the stairs in the dark
- **Rule:** lighting on landings (*palieres*) and stairs is controlled with push buttons and a staircase timer
  (*automático de escalera*) or with presence sensors, with times long enough to cover the flight. The lighting level must
  meet the minimums of the health and safety regulations, regardless of the minimum number of points.
- **Why:** it saves energy, but a badly set timer leaves someone in the dark on the stairs.
- **How:** push buttons with a pilot light on each landing; timer with a permanent-on position for maintenance; if you
  use sensors, cover the half-landings. Minimum points per 772.8.2.
- **Verify:** walk the stairs from top to bottom with the programmed time; measure the illuminance on the half-landings.
- **Don't:** supply the stairs from the caretaker's apartment (*depto*); use the timer as the only light on exits without
  emergency lighting (see ELEC-EDI-16).
- **Source:** AEA 90364-7-772 2019 ed., 772.1 (lighting sufficient for the minimums of the decrees under Ley 19587,
  regardless of the points in 772.8.2). **Not verified in a primary source:** specific times and levels for dwellings;
  check the municipal code.

### ELEC-EDI-16: Emergency lighting and signage on all means of egress
- **Rule:** the means of escape (landings, stairs, corridors, lobby, exit to the street, garages) have emergency lighting
  that turns on by itself when the mains fail, and exit signage. Published reference values (secondary source, they
  match the European standard EN 1838): **1 lx** at floor level on the centerline of the escape route, maximum/minimum
  ratio **40:1** and minimum autonomy **1.5 h** (value from the same technical note); confirm the autonomy with the text
  your jurisdiction requires.
- **Why:** a power cut and a fire are exactly the moments when people have to go down the stairs.
- **How:** self-contained units (with their own battery and charge indicator) or a central system; exit signs per
  IRAM 10005 (green with white); the supply circuit of the self-contained units has no switch accessible to the public,
  so they don't end up discharged. A generator set does not replace emergency lighting because it takes time to start.
  In workplaces, Decreto 351/79 has its own values; don't mix them.
- **Verify:** functional test by cutting the circuit (the unit must turn on instantly) and periodic full autonomy test;
  record the tests (ELEC-MED-22, ELEC-EDI-29).
- **Don't:** leave units with a dead battery or unplugged; use lamps that are slow to turn on.
- **Source:** values cited as those of IRAM-AADL J 2027 in "Iluminación de emergencia: normas y legislación vigente"
  (emergency lighting: current standards and legislation), Luminotecnia No. 139, 2017, Editores SRL (manufacturer's
  note); EN 1838 (1 lx on the centerline, 40:1) as a reference; Ordenanza CABA 45425/1991 (means of escape must have
  emergency lighting). **Not verified in a primary source:** the current edition and the values of IRAM-AADL J 2027 (in
  particular the autonomy and any higher requirement for premises with re-entry, which in the manufacturer's note seems
  taken from the British standard BS 5266), whether Ordenanza 45425 is still in force, and the equivalent article of the
  current Código de Edificación CABA (Buenos Aires City building code, Ley 6438).

### ELEC-EDI-17: Door entry, gate (*portón*), antennas and low-current systems: their own conduit and exposed metal parts earthed
- **Rule:** door entry/video door entry (*portero*/*videoportero*), TV, data, fiber optic, alarms and access control run
  in a riser (*montante*) or conduit of their own for low-current systems, separate from the power one, with their own
  junction boxes. The automatic gate has its own circuit and protection, with its RCD (*diferencial*). Antenna masts and
  outdoor metal equipment are bonded to the earthing system.
- **Why:** sharing a conduit with power induces noise and, in a fault, puts 220 V on a cable that people touch (the door
  entry handset). The gate is a motor outdoors.
- **How:** door entry power supply in the TP-SG or in a sub-panel (*tablero seccional*), with its MCB (*térmica*); gate
  motor with its MCB + 30 mA RCD and a local isolator; gate safety sensors (photocells) working; outdoor boxes with a
  suitable IP rating. Practical provision for new construction: a low-current riser with room for the fiber (FTTH) of more
  than one operator, a junction or distribution box on each floor, an empty conduit from that box to each apartment, and a
  socket outlet at the point where the operator's equipment or the IP video door entry will go.
- **Verify:** no box shares power and signals; the gate stops and reverses on an obstacle; mast connected to earth.
- **Don't:** supply the gate from a landing socket outlet with a power strip (*zapatilla*); run the door entry cable through
  the landing conduit.
- **Source:** AEA 90364-7-770 2017 ed., 770.10.3.8.2 h (in the dwelling, 380/220 V systems, MBTS/MBTF, low-current
  signals/video/TV/alarms and data must run in independent conduits; Note 1 gives alternatives only when separation is not
  possible) and 770.16.2.1 (telephone and data installations are allowed in the panel only if they serve its function).
  The provision for fiber from several operators is good practice, not an AEA requirement.
  **Not verified in a primary source:** a specific 772 requirement for low-current risers (the 2017 draft asked for LS0H communication cables) and the
  antenna earthing standard (IEC 60728-11).

### ELEC-EDI-18: Garages (*cocheras*) and electric vehicle charging: a dedicated circuit per charging point and power management
- **Rule:** each electric vehicle charging point has a dedicated circuit with its overcurrent protection and its own RCD
  of 30 mA at most, type A at least, plus protection against DC leakage: type B ID, or type A + RDC-DD DC detector
  (IEC 62955), or type F + RDC-DD, unless the charging station already provides it. In a building, plan from the design
  stage conduits and power for future chargers, or a load management system that does not exceed the contracted power.
- **Why:** the standard takes a simultaneity of 1 for charging points unless there is load control: five cars charging at
  7 kW add up to 35 kW, and with that alone the example building goes over the 60 kVA threshold (ELEC-EDI-2). A common RCD
  (type AC) can be blind to DC leakage from the charger.
- **How:** decide with the owners' association (*consorcio*) whether each charger hangs off the unit's meter (cable through
  the garage to its panel) or off common services with sub-metering; leave an empty conduit from each garage space to the
  riser or the meter cabinet; garages also have their own lighting and emergency lighting (ELEC-EDI-16). If the charger
  hangs off the unit, recalculate the demand, the line, the incoming switch and the contracted power of that unit: a 7 kW
  single-phase charger draws 7000 / 220 = 31.8 A and takes a 7 kVA apartment to about 14 kVA, which no longer fits on a
  32 A sub-main and may call for a three-phase supply; or use a charger with dynamic limiting based on the apartment's
  consumption. Spread the chargers across phases (ELEC-EDI-10). Details in ELEC-ESP-17 to ELEC-ESP-19 of
  [special-installations.md](special-installations.md).
- **Verify:** demand calculation report including the chargers (factor 1 or documented load control); correct RCD type;
  charger test.
- **Don't:** charge an apartment's car with an extension cord (*alargue*) from a common services socket outlet; add a
  charger to a unit without recalculating its line.
- **Source:** AEA 90364-7-722 2024 ed. (2nd ed., official extract published by AEA): 722.311 (diversity factor 1 unless
  there is load control), 722.411.3.3 (an individual RCD with IΔn ≤ 30 mA per connection point) and 722.531.2.101 (type A
  at least; protection against DC leakage with a type B ID, or type A or F with RDC-DD per IEC 62955, unless the charging
  station provides it).

### ELEC-EDI-19: Fire pump and pressurization: a supply that is not cut with the main switch
- **Rule:** usual design criterion (pending confirmation in the current text of 772/718 and in the building code): if the
  building has a fire pump, stair pressurization or smoke extraction, that equipment is supplied by a direct, dedicated
  circuit, connected so that the building's main cut-off (for example, the one firefighters use) does not leave it without
  power, with fire-resistant cables and permanently connected motors. What is mandatory is what the local code and the
  approved fire protection design say.
- **Why:** this is the equipment that has to work precisely during the fire; a thermal overload relay that trips on
  overload leaves the firefighters without water.
- **How:** a specific design with the fire protection professional; AEA 772 includes informative examples of single-line
  diagrams with fire protection installations and lightning protection for buildings **more than 25 m** tall (figures
  772.C.1 and 772.C.2) and of a fire pump room with an elevated tank (772.C.8). The firefighters' main cut-off goes where
  the code or the local fire department requires it (normally on the ground floor (PB), accessible from the common areas),
  marked, with a sign saying what it leaves live (fire pump, pressurization, and generator set or solar panels if there
  are any, ELEC-EDI-27). A typical PB + 4 usually has no fire pump, but confirm it with the local code.
- **Verify:** the route of the fire-resistant cable; start-up test with the main switch off, per the design; main cut-off
  sign legible.
- **Don't:** protect the fire pump with an ordinary motor protection circuit breaker (*guardamotor*) "like the others"
  unless the fire protection design specifies it.
- **Source:** AEA 90364-7-772 2019 ed., figures 772.C.1, 772.C.2 and 772.C.8 (official index; Annex C is informative);
  AEA 90364-7-718 2008 ed. **Not verified in a primary source:** supply ahead of the main cut-off, short-circuit-only
  protection, fire resistance classes (F30/F90) and location of the firefighters' cut-off: they appear in the 2017 draft
  of 772 and in 718 practices; confirm them in the current text and in the building code.

### ELEC-EDI-27: Generator set, UPS or solar panels on common services: never in parallel with the grid without permission
- **Rule:** if the owners' association installs a generator set or a UPS for the elevator, pumps or emergency lighting,
  the backup supply comes in through a transfer panel that makes it impossible to connect the generator and the grid at
  the same time (changeover switch with mechanical **and** electrical interlocking, also switching the neutral). Solar
  panels that feed into the grid are connected only after the user-generator procedure with the utility (distribution
  company) (Ley 27.424 or the provincial scheme) and with a bidirectional meter. Every panel with dual supply is marked.
- **Why:** a generator or an inverter that backfeeds the grid electrocutes the utility's staff working on a line they
  believe is dead, and makes the building dangerous for the electrician and the firefighters who switch off the main.
- **How:**
  1. Define which loads are essential (elevator with rescue, pumps, landing lights, pressurization) and build with them an
     essential loads panel behind the changeover switch.
  2. Automatic transfer switch or two contactors with mechanical and electrical interlocking; generator neutral referenced
     to earth when it runs in island mode (ELEC-ESP-25, ELEC-ESP-26).
  3. Generator in a ventilated room or outdoors, with the exhaust to the outside; if it goes in a room used only for
     electrical purposes, see 772.24.2.
  4. UPS with backfeed protection and signs on the circuits that stay live (ELEC-ESP-27).
  5. Panels: the procedure, a certified inverter and "dos fuentes" ("two sources") signs in the TP-SG and at the main
     cut-off (ELEC-ESP-20 to ELEC-ESP-23).
- **Verify:** with the changeover switch on "grupo" (generator) and the grid present, that there is no continuity between
  the two inputs (measured dead in each position); transfer test with the grid cut; dual supply signs in the TP-SG and at
  the firefighters' cut-off.
- **Don't:** connect the generator "through a socket outlet" or with a cable with two male plugs; use a changeover switch
  that switches only the phase; connect feed-in panels without notifying the utility.
- **Source:** AEA 90364 Part 5 (2006 ed.), clause 551 (generator sets, including 551.7, parallel with the grid), per
  ELEC-ESP-25; IT AEA 95511 2023 ed. (UPS); Ley 27.424 and Decreto 986/2018 (distributed generation), see ELEC-ESP-20;
  AEA 90364-7-772 2019 ed., 772.24.2 (room with a generator set, title per the index).
  **Not verified in a primary source:** the text of 772.24.2 and of AEA clause 551 (the no-parallel changeover criterion is that of IEC 60364-5-55,
  551.6).

## Earthing, equipotential bonding and lightning

### ELEC-EDI-20: A single earthing system for the whole building, with a main earthing bar and equipotential bonding
- **Rule:** the building has a single protective earthing system, with a main earthing bar (normally in the meter room)
  that receives: the electrodes (earth rods (*jabalinas*) and/or foundation electrode), the PE of each unit and of common
  services, the metal pipes entering the building, the metal structure, the elevator guide rails and the lightning
  protection down conductors if there are any. The earthing arrangement for users supplied from the public LV grid is TT:
  the protective earth electrode is electrically independent of the utility's service earth, and the utility's neutral is
  not connected to the exposed conductive parts inside the building.
- **Why:** several separate electrodes for different things in the same building create dangerous potential differences
  between exposed parts a person can touch at the same time (for example, the faucet and the refrigerator).
- **How:** each line to a unit carries its PE from the main bar (ELEC-EDI-7); resistance value and electrode design per
  [earthing.md](earthing.md): in 770, **Ra ≤ 40 Ω** measured on the set of electrodes disconnected, a value tied to RCDs
  with IΔn ≤ 300 mA (ELEC-PAT-9); lower values as a design target. The protective earth electrode goes inside the property
  and more than 10 equivalent radii from the utility's nearest service earth; if there is a transformer vault in the
  building and that is not possible, see ELEC-PAT-15. Earthing conductor of the service connection per the utility's
  diagram (Edenor's show a 2 m copper-clad steel earth rod with an inspection box). Bonding of gas pipes is done as the gas
  distribution company indicates.
- **Verify:** earth resistance measurement with an earth resistance tester (*telurímetro*), with the electrode
  disconnected; continuity of each unit's PE to the bar; equipotential bonds accessible and labeled (see
  [testing-and-commissioning.md](testing-and-commissioning.md)).
- **Don't:** use the neutral as earth; drive one earth rod per apartment in the yard; leave the earthing bar unidentified;
  take the earth from the transformer vault's grid without a design or authorization.
- **Source:** AEA 90364-7-770 2017 ed., 770.3.2 (TT system required; protective earth independent of the service earth;
  Ra ≤ 40 Ω), 770.14.3 b (ID ≤ 300 mA with Ra ≤ 40 Ω), 770.14.4.1 (measurement on the set of electrodes disconnected) and
  770.14.4.2 (more than 10 equivalent radii from the service earth, inside the property); AEA 95501-3 / IRAM 2281-3
  2024 ed. (earthing of installations up to 1 kV, AEA catalog); AEA 90364-7-772 2019 ed., 772.7.2 (earthing arrangements)
  and Annex B (cable entry into a metal panel in TT); Ingeniería Eléctrica, "Puesta a tierra" (earthing) (A. Farina, 2024),
  as a secondary source; Edenor diagrams in Ingeniería Eléctrica No. 327 (2017). **Not verified in a primary source:** the
  content of AEA 95501-3 2024 ed. and the table of maximum values by RCD sensitivity (771.3.I) in its current edition.
### ELEC-EDI-21: Lightning protection (*pararrayos*) follows from a risk assessment; if there is one, it is bonded to the common earth and has SPDs (*DPS*)
- **Rule:** the need for a lightning protection system (SPCR, *sistema de protección contra rayos*) is determined with the
  risk assessment of AEA 92305-2 / IRAM 2184-2 and with what the municipality requires. If one is installed, its down
  conductors are bonded to the building's common earthing system, and coordinated surge protective devices, SPDs (*DPS*),
  are installed in the main panel and in the sub-panels (*tableros seccionales*).
- **Why:** a lightning strike on a building without equipotential bonding jumps to the pipes and to the electrical
  installation; an SPCR with a separate earth makes things worse.
- **How:** design by a professional; air terminals, down conductors and electrodes per AEA 92305-3; type 1 SPD at the
  origin if there is an SPCR, type 2 downstream (see ELEC-PRO-16 to ELEC-PRO-18). In TT, an SPD upstream of the RCD
  (*diferencial*) goes in a **1+1** (single-phase) or **3+1** (three-phase) configuration, with an N-PE spark gap;
  connections as short as possible (**0.5 m** in total at most). In a collective cabinet, agree with the utility
  (distribution company) where "the origin" is: in the TP-SG and in each unit's main panel (user side), or in the
  apartments' (*deptos*) panels; never inside the sealed module.
- **Verify:** the risk assessment report; continuity of down conductors; connections to the common earth; condition of the
  SPDs (indicator window); connection length measured.
- **Don't:** install a "lightning rod" (*pararrayos*) spike without a design, with a down conductor inside the building, or
  with its own earth rod (*jabalina*) not bonded.
- **Source:** AEA 92305-1/-2/-3/-4 (IRAM 2184-1 to -4), 2015 ed., and 92305-11, 2016 ed. (AEA catalog); AEA 90364-7-772
  2019 ed., figures 772.C.1/C.2 (single-line diagrams with SPCR for buildings more than 25 m tall); IEC 60364-5-53,
  section 534 (SPD configurations in TT and connection length), per ELEC-PRO-18. **Not verified in a primary source:** a
  height threshold above which CABA or another municipality requires lightning protection.

### ELEC-EDI-22: Power factor of the owners' association (*consorcio*) (Edenor/Edesur area): automatic correction to 0.95
- **Rule:** in a condominium building (*propiedad horizontal*) with a common service connection, the reactive energy
  surcharge applies to the **common supply of the owners' association** (*consorcio*) (common services, T1G) that has a
  meter able to measure reactive energy; individual residential apartments (T1 residencial) are not surcharged. To avoid
  it, the owners' association installs, if the building allows it, an **automatic** power factor correction unit that
  brings cos φ to **0.95**, and notifies the utility.
- **Why:** according to the trade press, Res. ENRE 628/2024 raised the minimum cos φ from 0.85 to **0.95** in the
  Edenor/Edesur area, with a surcharge of 1.5 % for each hundredth below 0.95 and a cap of **40 %**, applied gradually:
  30 % of the surcharge until 2025-04-30, 60 % from 2025-05-01 and **100 % from 2025-12-01**.
- **How:** load study (measurement with a power analyzer for at least one week), automatic unit with a controller,
  connected at the point the utility indicates; periodic maintenance of capacitors. According to the summary of an
  association of condominium owners, the resolution also prohibits fixed capacitors unless authorized, requires
  anti-resonance (detuning) reactors if the total voltage harmonic distortion is **≥ 7 %**, and does not allow the utility
  to charge for inspection or approval of the unit: confirm it in the official text.
- **Verify:** cos φ measured ≥ 0.95 on the bill or with an analyzer. To check inside the unit (swollen capacitors, blown
  fuses): **a capacitor bank holds a dangerous charge after it is switched off.** Switch the unit off, wait the discharge
  time the manufacturer indicates (standard discharge devices bring the voltage down to 75 V or less in 3 minutes at most)
  and verify absence of voltage at the capacitor terminals before touching.
- **Don't:** hang fixed capacitors "by eye": at low-load hours they overcompensate and can resonate with harmonics; open
  the unit right after switching it off.
- **Source:** Res. ENRE 628/2024 (B.O., Official Gazette, 2024-09-11), through secondary sources: iProfesional, "Qué pasó
  con los polémicos tableros de Edenor y Edesur y cuándo llegarán las multas" (what happened with the controversial Edenor
  and Edesur panels and when the fines will come) (0.95; 1.5 % per hundredth; 40 % cap; schedule; exclusion of T1
  residential and individual units) and a summary by Liga del Consorcista (fixed capacitors, 7 %, no inspection charge);
  IEC 60831-1 (discharge to ≤ 75 V in ≤ 3 min). **Not verified in a primary source:** the text and articles of
  Res. ENRE 628/2024, and whether ENReGE amended it; check the Boletín Oficial before advising an owners' association.

## Building code and construction stages

### ELEC-EDI-23: Check with the municipality what the building code requires that affects the electrical work
- **Rule:** before closing the electrical design, confirm with the local building code: whether an elevator is required by
  number of floors or accessibility, emergency lighting and signage on means of egress, the meter room, fire protection
  systems by height and use, and whether lightning protection is mandatory.
- **Why:** those requirements change the load (elevator, pressurization) and the meter room; they are municipal and vary.
- **How:** in CABA the Código de Edificación (building code, Ley 6100, amended by Ley 6438) applies, with technical
  regulations (RT); for example, the RT for individual and collective housing (RT-030809-020309-01, v4, Aug 2023) allows,
  in collective housing with units on the ground floor (PB) and one upper floor, leaving the shaft ready for a future
  elevator (type 1 car), without replacing it with another mechanical means. In other cities, ask the municipality or the
  professional council for the local code.
- **Verify:** a checklist signed by the architect/construction director with the applicable articles.
- **Don't:** assume that the CABA code applies in the provinces or vice versa.
- **Source:** GCBA, RT-030809-020309-01 version 4 (IF-2023-32032403-GCABA-SSGU), art. 3.8.9.1 C.E.; Ordenanza CABA
  45425/1991. **Not verified in a primary source:** the current article that sets from how many floors an elevator is
  mandatory in CABA, and the electrical requirements for means of egress in the current text of the code.

### ELEC-EDI-24: Conduits in the structural stage with an approved drawing; inspection before covering
- **Rule:** conduits, boxes and risers (*montantes*) are installed during the structural stage (*obra gruesa*) (in slabs
  before the concrete pour and in masonry before plastering) following the signed design. The Construction Director
  (*Director de Obra*) (or, failing that, the installer) formally requests (*en forma fehaciente*) the inspection from
  the Enforcement Authority or Control Body of their jurisdiction, at least **before covering** conduits and embedded or
  concealed elements, and **before commissioning**.
- **Why:** what is left inside a slab cannot be corrected; a crushed conduit or a missing box is discovered when pulling
  cable, when breaking things open costs a great deal.
- **How:** by stages:
  1. **Design:** drawings and technical report signed by a licensed or registered professional with the relevant scope
     (*incumbencia*); the utility's feasibility approval (ELEC-EDI-1); standard for each unit (ELEC-EDI-26); municipal
     approval if applicable.
  2. **Site compound (*obrador*):** temporary construction supply (meter pillar (*pilar*) or construction meter, per the
     utility) with a construction site panel per AEA 90364-7-704 (2026 ed.); see [site-safety.md](site-safety.md) and
     [regulations-and-permits.md](regulations-and-permits.md).
  3. **Foundations:** foundation electrode or provision for earth rods and for the earthing conductor to the meter room.
  4. **Slabs:** conduits suitable for embedding in concrete (IRAM standardized, not uncertified corrugated conduit), tied
     to the reinforcement, ends capped, ceiling boxes fixed; a photo of each slab before the pour.
  5. **Masonry:** drops, boxes level, risers in shafts with a junction box on each floor; a draw wire in each run.
  6. **Inspection before covering** (formal request and a record with date and signature).
  7. **Cable pulling** after plastering, with clean, dry conduits; **panels**; labels.
  8. **Tests**, inspection before commissioning, and connection (ELEC-EDI-25).
- **Verify:** photos per slab and per floor; proof of the request and the record of the inspection before covering; drawing
  updated with changes.
- **Don't:** pull cable before the base plaster coat (water and lime damage the insulation); cut reinforcement bars to pass
  conduits; treat the construction director's signature as if it were the authority's inspection.
- **Source:** AEA 90364-7-770 2017 ed., 770.2.1 (design with drawings and report signed by a licensed or registered
  professional with the relevant scope) and 770.2.2 a-b (the Construction Director or the Installer requests the
  inspection before covering and before commissioning); AEA 90364-7-772 2019 ed., 772.4.1 to 772.4.3 (design, minimum
  contents, verification during installation); AEA 90364-7-704 2026 ed. (AEA catalog).

### ELEC-EDI-25: Tests, DCI, utility connection and as-built documentation
- **Rule:** before requesting the permanent connection, the installation tests are carried out and recorded (PE
  continuity, insulation, earth resistance, RCD test, polarity, phase rotation on three-phase supplies); the professional
  or installer with the relevant scope issues the declaration of conformity of the internal electrical installations
  (DCI, installation conformity declaration) where it is required; the utility installs the meters; the as-built
  documentation is handed over to the owners' association.
- **Why:** the utility does not connect without the documentation it requires; the owners' association needs the real
  drawings to maintain and repair without guessing.
- **How:** tests per AEA 90364-6 (2025 ed.) and [testing-and-commissioning.md](testing-and-commissioning.md). In the
  Edenor/Edesur area, each new single-phase T1R supply (each apartment) requires a DCI or an equivalent municipal document;
  the common services supply (T1G) and three-phase supplies require municipal approval or a final construction inspection,
  or the start of the procedure plus a DCI (details in ELEC-NOR-10 of [regulations-and-permits.md](regulations-and-permits.md)).
  In other jurisdictions the local certificate or standard applies. Only once the permanent meters are installed are the
  units energized; the construction site panel is decommissioned as the utility indicates. Final folder: single-line
  diagrams of the TP-SG and of each sub-panel, riser drawing with the phase and conduit of each unit, calculation report,
  test records, elevator/pump/emergency lighting manuals, maintenance plan (ELEC-EDI-29).
- **Verify:** signed test record; DCI or approval submitted for each supply; meters installed and sealed; correct voltage
  and phase rotation in each unit and at the elevator/pumps on energizing.
- **Don't:** energize units "hung" off the common services meter or the construction pillar while waiting for the meters;
  hand over the building without single-line diagrams.
- **Source:** AEA 90364-6 2025 ed. (verification of installations, AEA catalog); AEA 90364-7-772 2019 ed., 772.4.4
  (as-built documentation) and 772.23 (initial and periodic verification, maintenance); ENRE Res. 225/2011, Reglamento
  para la conexión de nuevos suministros (regulation for connecting new supplies) (2022 edition of the text on
  argentina.gob.ar), sections II and III (declaration of conformity by professionals, technicians or installers with the
  relevant scope, in accordance with the current AEA Reglamentación) and Res. ENRE 269/2012 (DCI form), per ELEC-NOR-10;
  Reglamento de Suministro ENRE (ENRE supply regulation) art. 2 inc. c and d (protection and maintenance downstream of
  the first isolation point per the AEA). **Not verified in a primary source (in this review):** the text of the connection
  regulation, which was taken from ELEC-NOR-10; the rule that makes the DCI mandatory in each jurisdiction outside the ENRE
  area.

## Existing buildings and maintenance

### ELEC-EDI-28: Existing building: before adding load, check the riser (*montante*), the line and the contracted power
- **Rule:** in an existing building, increasing the power of a unit (air conditioner, induction cooktop, electric water
  heater, EV charger) requires checking its line up the riser (*montante*), its incoming switch and its contracted power,
  and requesting the increase from the utility. Old risers (cable with cloth or rubber insulation, aluminum, cross-sections
  of 2.5 or 4 mm², no PE, several units in one conduit) are replaced with lines per ELEC-EDI-7 and ELEC-EDI-8.
- **Why:** this is the most frequent case in practice: a riser designed for a refrigerator and lights now carries two or
  three ACs per apartment; the cables heat up, the splices loosen, and broken (lost) neutrals and fires in the shaft
  appear. Also, increasing demand without the utility's authorization makes the user liable for damage to the meters.
- **How:**
  1. As-found survey (*relevamiento*), with the power off, of each line (cross-section, material, insulation, PE, conduit, splices)
     and of the meter cabinet; thermography under load by trained personnel (ELEC-MED-23).
  2. Calculation of each unit's new demand ([grades-and-circuits.md](grades-and-circuits.md), ELEC-DIA-21 to
     ELEC-DIA-23) and of the line with `gateway electricidad`.
  3. Request for a power increase to the utility; if the main panel's protection devices or the service connection
     change, the increase requires a DCI in the Edenor/Edesur area (ELEC-NOR-10). If the building total goes over 60 kVA,
     the utility may ask for a transformer substation (CT) (ELEC-EDI-2).
  4. Riser replacement in stages, unit by unit, with that unit's incoming switch off and locked out, and the neighboring
     lines identified and protected (ELEC-EDI-7, Verify). If the meters are on each floor and are moved to the ground floor
     (PB), it is a job with the utility: it disconnects, relocates and seals.
  5. When finished, tests of the unit worked on and an update of the riser drawing (ELEC-MED-20).
- **Verify:** a schedule per unit with the new contracted power, cross-section and protection; proof of the power
  increase; voltage drop of the farthest apartment measured under load.
- **Don't:** raise the rating of the incoming switch so it "doesn't trip" with the same line (ELEC-PRO-6); pull a new cable
  through a conduit occupied by another unit's live line; touch splices in an old riser without switching off all the
  units that pass through that box.
- **Source:** Reglamento de Suministro ENRE art. 2 inc. a (sworn declaration and data updates) and inc. d (user liability
  if the declared demand is increased without authorization; maintaining the installation per the AEA); ENRE
  Res. 225/2011 (2022 edition of the text) and the Edesur guide on the DCI (power increase that involves changing
  protection devices), per ELEC-NOR-10; AEA 90364-7-722 2024 ed., 722.6.4.1 (check the existing installation when adding
  chargers), per ELEC-ESP-19. The list of typical defects of old risers is field practice, not text from a standard.

### ELEC-EDI-29: Owners' association (*consorcio*) maintenance: annual plan, safe method and records
- **Rule:** the owners' association has a written electrical maintenance plan, with periodic inspection by a professional
  or qualified installer, and a record of each test. Every adjustment or intervention is done dead, with isolation and
  lockout; thermography and live measurements are done only by trained personnel with PPE (*EPP*).
- **Why:** loose terminals, dead emergency batteries and stuck RCDs give no warning: they show up on the day of the fire
  or the power cut. A signed record also helps the building management with the insurer and the municipality.
- **How:** indicative minimum plan:
  - Monthly: test button of the common services (SG) RCDs; functional test of the emergency lighting.
  - Annual: RCD test with an instrument; full autonomy test of the emergency lighting; thermography of the TP-SG and of
    the elevator and pump panels under load (ELEC-MED-23); panel inspection and terminal tightening **with the power off**;
    condition of the SPDs and of the power factor correction unit (ELEC-EDI-22).
  - Periodic: earthing measurement and PE continuity; full inspection of the common installation at the frequency the
    jurisdiction sets (ELEC-MED-19, ELEC-NOR-17).
  - Record: date, who, what was measured, values, actions. Elevator and pumps: in addition, whatever the maintenance
    company and the municipal register require.
- **Verify:** logbook or schedule up to date; date of the next inspection visible in the TP-SG.
- **Don't:** send the caretaker to "tighten the panel"; open inner covers (*contratapas*) live to take a look.
- **Source:** AEA 90364-7-772 2019 ed., 772.23 (initial and periodic verification, maintenance); AEA 90364-6 2025 ed.;
  ENRE Res. 225/2011 (2022 edition of the text), section III point 5 (inspection frequency by type of use), per
  ELEC-NOR-17. **Not verified in a primary source:** the exact frequencies of 772.23 and of 90364-6, and the municipal
  obligations for periodic inspection of electrical installations in each city; check with the municipality.

---
## Example case: ground floor + 4 floors, 8 single-phase apartments

Assumptions (illustrative, to show the method; in a real design every number comes from the standard and the calculator):

- 4 upper floors × 2 apartments (*deptos*) = 8 single-phase 220 V units with natural gas; DPMS (maximum simultaneous
  power demand) of each: **7 kVA** (calculated per [grades-and-circuits.md](grades-and-circuits.md)). Incoming switch
  ≤ 63 A and reported Icc ≤ 10 kA; each apartment is designed with 771 (ELEC-EDI-26). 7 kVA is around the top of the Medium grade in 771 (table 771.8.I); with a
  TUE for the air conditioner the total goes over it, the unit becomes High (factor 0.8, requires 2 IUG) and the
  calculator gives 6952 VA (31.6 A): apartment 4A in [examples/README.md](examples/README.md).
- Common services: three-phase elevator 5.5 kVA; 2 lift pumps of 1.1 kW (one on standby, count one ≈ 1.5 kVA);
  landings + emergency lighting + door entry + gate ≈ 1.5 kVA. Total common services (SG) ≈ **8.5 kVA**.
- Diversity (simultaneity) factor for 8 units: **0.8** (illustrative value, equal to the optional precedent in table
  771.9.III for 5 to 15 units of Minimum or Medium grade; the real one comes from table 772.9.III).

**Building demand**

| Item | Calculation | Result |
|---|---|---|
| Units | 8 × 7 kVA × 0.8 | 44.8 kVA |
| Common services | 5.5 + 1.5 + 1.5 | 8.5 kVA |
| Total | 44.8 + 8.5 | **53.3 kVA** |
| Current per phase (if it were balanced) | 53 300 / (√3 × 380 V) | ≈ 81 A |
| Most loaded phase (L1/L2, see the split) | 19 100 VA / 220 V | **≈ 87 A** |

To check fuses and conductors upstream (the utility (distribution company) defines them), the most loaded phase governs,
not the balanced average. 53 kVA is below 60 kVA, but close: with four or five EV chargers or air conditioning in every
room it goes over. Ask about the transformer substation in the feasibility request (ELEC-EDI-2) and redo the calculation
with the real table: `gateway electricidad building --units 8 --dpms 7000 --grade high --common-3ph 7000
--common-1ph 1500 [--coef X]` (DPMS of each unit with `demand --norm 771`; `--coef` with the value from table 772.9.III or
the one the utility asks for). It splits the units by phase and gives the current of the most loaded phase.

**"All-electric" variant (no gas):** with induction and an electric water heater the DPMS per apartment goes up; with
10 kVA per apartment: 8 × 10 × 0.8 + 8.5 = **72.5 kVA** (≈ 110 A per phase balanced), above 60 kVA: the utility may ask
for the transformer substation, and some apartments could move to three-phase (more than 7 kVA or 32 A, 771.9.3.3).
Watch the factor: 10 kVA is already High grade, and the precedent 771.9.III gives 0.6 for 5 to 15 High units
(8 × 10 × 0.6 + 8.5 = 56.5 kVA); with table 772.9.III in hand the result can land on either side of 60 kVA: request
the feasibility with the calculation done using the real table.

**Phase split (ELEC-EDI-10)**

| Phase | Units | Other loads | Approx. demand |
|---|---|---|---|
| L1 | 1A, 2B, 4A | 1/3 elevator + pump | 3 × 7 × 0.8 + 2.3 ≈ 19.1 kVA (≈ 87 A) |
| L2 | 1B, 3A, 4B | 1/3 elevator + pump | 3 × 7 × 0.8 + 2.3 ≈ 19.1 kVA (≈ 87 A) |
| L3 | 2A, 3B | 1/3 elevator + pump + landings/emergency lighting/door entry/gate | 2 × 7 × 0.8 + 2.3 + 1.5 ≈ 15.0 kVA (≈ 68 A) |

The table uses the 8-unit factor (0.8) for groups of 2 or 3 apartments: this is an optimistic approximation, because the
simultaneity of a few units is higher. With, for example, 0.9 for 3 units, L1 would give 3 × 7 × 0.9 + 2.3 ≈ 21.2 kVA
(≈ 96 A). L3 is left somewhat lighter; if a single-phase shop is later added on the ground floor (PB), it goes on L3. A
single 7 kW charger on L3 takes it to 15.0 + 7 = 22.0 kVA (≈ 100 A), more than L1 and L2: spread the chargers across
phases or use three-phase chargers or chargers with load management (ELEC-EDI-18).

**Line to each apartment (ELEC-EDI-8):** each apartment's incoming switch in the meter room (at ≤ 2 m), sub-main (feeder)
up the riser (*montante*). For the 4th floor (≈ 20 m), 32 A: 6 mm² gives 1.92 % drop, 10 mm² gives 1.14 % and 16 mm²
gives 0.72 %; with the 1 % that 771 requires on the sub-main, **16 mm² in R32 conduit** (10 mm² in R25 only if the authority accepted 770 for the apartments). For the lower floors the drop is smaller and a smaller cross-section is enough; many jobs use the same cross-section for all
units to keep it simple. If an apartment adds an EV charger, its 32 A line is not enough (ELEC-EDI-18).

**Protection for each apartment:** voltage protector (over/undervoltage relay) against a broken (lost) neutral
(ELEC-EDI-11), RCD (*diferencial*) and MCBs (*térmicas*) per [protection.md](protection.md). To review an apartment panel
that is already built (for example, from a photo), follow [reviewing-a-panel.md](reviewing-a-panel.md).

## Common mistakes in buildings

| What you see | Problem | Rule |
|---|---|---|
| Appliances burned out in several apartments on the same day, others with dim lights | Broken or loose connection of the common neutral | ELEC-EDI-11 |
| Fuses on one phase that blow repeatedly (the utility detects it) or very uneven readings per unit | Units badly split across phases | ELEC-EDI-10 |
| Top-floor apartment with low voltage when the AC starts | Long sub-main with a small cross-section | ELEC-EDI-8 |
| The riser cables can't be pulled | R19 conduit for 10 or 16 mm² | ELEC-EDI-7 |
| All the units' cables in the same riser conduit | Grouping prohibited with single-core cables | ELEC-EDI-7 |
| Riser shaft open between floors | No fire-stop sealing | ELEC-EDI-7 |
| A fault in an apartment or at the pump shuts down the whole building | Incoming RCD not selective or more sensitive than the ones downstream | ELEC-EDI-12 |
| Stairs in the dark when the power goes out | Emergency lighting missing or with a dead battery | ELEC-EDI-16 |
| RCDs trip when the elevator starts | RCD not suitable for the drive (VFD) or leakage | ELEC-EDI-13 |
| Pump burned out, cistern empty | No low-level cut-off | ELEC-EDI-14 |
| Reactive energy surcharge on the owners' association (*consorcio*) bill | No automatic power factor correction | ELEC-EDI-22 |
| Lightning protection earth rod (*jabalina*) separate from the building earth | Missing equipotential bonding | ELEC-EDI-20, ELEC-EDI-21 |
| Old riser that heats up since ACs were installed | Undersized line, no power increase | ELEC-EDI-28 |
| Generator set plugged into a common services socket outlet | Backfeed to the grid | ELEC-EDI-27 |

## What this guide does not replace

- The **design**, the calculations and the sign-off of the installation are done by a professional or qualified installer
  according to the jurisdiction (license (*matrícula*), category and scope (*incumbencias*)), and that person is
  responsible for them.
- The **utility** decides the type of supply, the location and model of the utility service box (*caja de toma*) and the
  meter cabinet, the need for a transformer substation, the phase of each unit and the connection conditions; the
  **municipality** decides the building code matters (elevator, means of egress, fire, technical rooms) and the approvals.
- The AEA and IRAM standards cited are paid: here they are summarized and clauses are cited; to design you need the
  current text your jurisdiction requires (770 has a 2026 edition and the clauses cited here are from the 2017 edition).
- Never work live. Everything before the first isolation point (service box, fuses, meters) is operated only by the
  utility.
