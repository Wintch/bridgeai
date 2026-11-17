---
title: Vehicles guide for Argentina (index)
scope: private cars in Argentina: traffic law and road signs, fines and the points licence, tolls and TelePASE, insurance, the registry and inspection paperwork, trip preparation and border crossings, general maintenance, and the first-generation VW Gol (model year 1994) in depth; the knowledge base of the bridgeai `vehiculos` pack
when_to_use: start here for any vehicle question; find the document for the situation and cite the rule by its ID
related: [traffic-law.md, road-signs.md, fines-and-points.md, tolls-and-telepase.md, insurance.md, ownership-and-paperwork.md, trip-preparation.md, car-maintenance-basics.md, vw-gol-1994-specs.md, vw-gol-1994-repairs.md, GLOSSARY.md, RULES.md]
as_of: 2026-11-15
sources: [Ley 24.449 and Decreto 779/95 as changed by Decreto 32/2018, 26/2019 and 196/2025 (new Anexo L), Ley 26.363, Ley 27.714, PBA Ley 13.927 and Ley 15.657, CABA Ley 2148, Ley 17.418, SSN resolutions, DNRPA dispositions, PBA Ley Impositiva 2026, TelePASE and concessionaire terms, the workshop manual "Manual de reparación y ajustes - Gol" and Argentine and Brazilian VW owner's manuals (see each document)]
---
# Vehicles guide

Reusable knowledge for drivers and owners of private cars in Argentina, many of them with old cars and some doing their own
basic repairs. The agent of the `vehiculos` pack reads it in `/usr/local/share/aibridge/vehiculos/` and cites each rule by its
ID ("VEH-MUL-10: pay inside the voluntary window to get the 50 % reduction"). Every rule has the same six fields (Rule, Why,
How, Verify, Don't, Source), so a person or an assistant finds the one that applies and reads only that.

**What it is and is not.** Legal and administrative content is information, not legal advice: the coupon, the court, the
insurer's policy and the official site decide. Amounts (fine units, fees, tolls, insured limits) are dated examples with the
place to check them. Repairs that can kill (brakes, fuel, working under a car, a hot cooling system) say so and say when a
mechanic is needed. Volatile facts changed a lot in 2025-2026 (Decreto 196/2025 rewrote much of the national regulation,
digital licence, new inspection periods, TelePASE deadlines): each document says what it could not confirm.

**Jurisdiction.** National law first; the province of Buenos Aires (PBA) and the City of Buenos Aires (CABA) are the worked
cases. Where they differ it matters: alcohol is zero nationally and in PBA but 0.5 g/l for private cars in CABA; CABA requires
a reflective vest and low beams 24 h on its motorways; PBA did not adopt the 2025 national inspection periods; PBA Ley 15.657
(2026) gives avenues priority over streets entering from the right. Ask where the person drives when it changes the answer.

**The VW Gol section.** It is written for the first-generation Gol ("Gol cuadrado", BX platform) GL 1.6 with the AP-1600
engine (code UN) and the two-barrel Weber DMPV carburettor, as sold in Argentina around 1994. Its main source is the
workshop manual "Manual de reparación y ajustes - Gol", whose "Gol GL / before 1996" sections cover this car (the rest of that
book is the second generation). The manual contradicts itself in places (initial advance 9° vs 13°, tyre pressures, gearbox
oil): VEH-GOL-43 lists each conflict and the value adopted.

## Find the document for your situation
| Situation | Read |
|---|---|
| Stopped by the police: which papers, what they may do (retention, towing) | [traffic-law.md](traffic-law.md) (VEH-LEY-12, 18, 46 to 48) |
| Is the digital licence or vehicle card in Mi Argentina valid? | [traffic-law.md](traffic-law.md) (VEH-LEY-10, 13) |
| Driving with an expired inspection (*VTV vencida*) | [traffic-law.md](traffic-law.md) (VEH-LEY-15, 16), [ownership-and-paperwork.md](ownership-and-paperwork.md) (VEH-DOC-27) |
| Mandatory equipment: fire extinguisher (*matafuego*), warning triangles (*balizas*), vest | [traffic-law.md](traffic-law.md) (VEH-LEY-19 to 21, 25), [trip-preparation.md](trip-preparation.md) (VEH-VIA-12) |
| Alcohol and speed limits where I drive | [traffic-law.md](traffic-law.md) (VEH-LEY-29, 30, 43, 49) |
| Who has priority at a corner or a roundabout | [traffic-law.md](traffic-law.md) (VEH-LEY-33, 34, 38) |
| Children in the car: child seat, back seat | [traffic-law.md](traffic-law.md) (VEH-LEY-23) |
| A crash: the driver's legal duties | [traffic-law.md](traffic-law.md) (VEH-LEY-50 to 52) |
| What a sign, a line or a flashing light means (*¿qué significa esta señal?*) | [road-signs.md](road-signs.md) (VEH-SEN-2, 5, 18, 26, 31, 32) |
| Level crossing (*paso a nivel*): what to do when a train comes | [road-signs.md](road-signs.md) (VEH-SEN-19, 35, 36), [traffic-law.md](traffic-law.md) (VEH-LEY-41) |
| A camera ticket and the sign was missing or hidden | [road-signs.md](road-signs.md) (VEH-SEN-39, 42 to 45), [fines-and-points.md](fines-and-points.md) (VEH-MUL-26 to 29) |
| My car was towed (*me acarrearon el auto*), no-parking signs and kerbs | [road-signs.md](road-signs.md) (VEH-SEN-12, 29, 40), [traffic-law.md](traffic-law.md) (VEH-LEY-44, 48) |
| A fine (*multa*): how much I really owe and where to check it | [fines-and-points.md](fines-and-points.md) (VEH-MUL-1, 5 to 7) |
| Pay with the 50 % off or file a defence (*descargo*)? | [fines-and-points.md](fines-and-points.md) (VEH-MUL-10, 16 to 18); `gateway vehiculos fine` |
| Do fines expire (*prescripción*)? | [fines-and-points.md](fines-and-points.md) (VEH-MUL-25) |
| Licence points (*scoring*): how many, what happens at zero | [fines-and-points.md](fines-and-points.md) (VEH-MUL-30, 33, 34) |
| Licence renewal blocked by fines | [fines-and-points.md](fines-and-points.md) (VEH-MUL-13, 36, 37) |
| Buying or selling a car with fines | [fines-and-points.md](fines-and-points.md) (VEH-MUL-21, 39, 40) |
| A message with a link to pay a fine or a toll | [fines-and-points.md](fines-and-points.md) (VEH-MUL-41, 42), [tolls-and-telepase.md](tolls-and-telepase.md) (VEH-PEA-27) |
| Getting TelePASE (the toll tag) | [tolls-and-telepase.md](tolls-and-telepase.md) (VEH-PEA-4, 5, 7) |
| I drove a tag-only highway without TelePASE (*pasé sin TelePASE*) | [tolls-and-telepase.md](tolls-and-telepase.md) (VEH-PEA-3, 9, 19) |
| The tag was not read, the barrier did not open | [tolls-and-telepase.md](tolls-and-telepase.md) (VEH-PEA-11 to 13) |
| Sold the car with the tag on | [tolls-and-telepase.md](tolls-and-telepase.md) (VEH-PEA-22, 23) |
| Tolls on national routes and the 2026-2027 changes; tolls in Uruguay, Chile, Brazil | [tolls-and-telepase.md](tolls-and-telepase.md) (VEH-PEA-3, 18, 20, 28 to 30) |
| An accident: what to do, the claim report (*denuncia de siniestro*) | [insurance.md](insurance.md) (VEH-SEG-12, 18 to 22), [trip-preparation.md](trip-preparation.md) (VEH-VIA-37) |
| The insurance lapsed, the direct debit failed | [insurance.md](insurance.md) (VEH-SEG-9, 31) |
| Cancel or suspend the insurance of a car I do not use | [insurance.md](insurance.md) (VEH-SEG-28, 29, 32) |
| Insurance for a 30-year-old car | [insurance.md](insurance.md) (VEH-SEG-13, 14, 27) |
| The insurer does not answer or pays late | [insurance.md](insurance.md) (VEH-SEG-11, 16, 17) |
| Driving to Chile, Uruguay or Brazil: insurance, papers, a driver who is not the owner, children | [insurance.md](insurance.md) (VEH-SEG-26), [trip-preparation.md](trip-preparation.md) (VEH-VIA-39 to 44) |
| Bought an old car: which papers; sold it and the buyer never transferred it | [ownership-and-paperwork.md](ownership-and-paperwork.md) (VEH-DOC-8 to 12, 14, 15) |
| Technical inspection (*VTV*): when, how much, booking | [ownership-and-paperwork.md](ownership-and-paperwork.md) (VEH-DOC-23 to 27) |
| Lost the vehicle card (*cédula*), title or licence | [ownership-and-paperwork.md](ownership-and-paperwork.md) (VEH-DOC-3, 5, 6, 32, 33) |
| Let someone else drive my car (the old *cédula azul*) | [ownership-and-paperwork.md](ownership-and-paperwork.md) (VEH-DOC-4) |
| Vehicle tax (*patente*) on an old car; is a 1994 car a classic? | [ownership-and-paperwork.md](ownership-and-paperwork.md) (VEH-DOC-19 to 21, 34) |
| A long trip: what to check before | [trip-preparation.md](trip-preparation.md) (VEH-VIA-1 to 10, 49) |
| Ruta 40 and Patagonia: fuel stops, gravel (*ripio*), wind | [trip-preparation.md](trip-preparation.md) (VEH-VIA-16, 24, 25); `gateway vehiculos trip` |
| The old car overheats in summer heat | [trip-preparation.md](trip-preparation.md) (VEH-VIA-31, 32), [car-maintenance-basics.md](car-maintenance-basics.md) (VEH-MAN-23), [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-7, 24 to 26) |
| Broke down on the road: where to stop, whom to call | [trip-preparation.md](trip-preparation.md) (VEH-VIA-34 to 36) |
| Mountain passes, snow chains, the Cristo Redentor pass | [trip-preparation.md](trip-preparation.md) (VEH-VIA-29, 45) |
| The car will not start (*no arranca*), noises, leaks, smoke | [car-maintenance-basics.md](car-maintenance-basics.md) (VEH-MAN-21, 22, 24 to 28) |
| A warning light came on in the dashboard | [car-maintenance-basics.md](car-maintenance-basics.md) (VEH-MAN-20) |
| Flat battery, jump start (*pasar corriente*) | [car-maintenance-basics.md](car-maintenance-basics.md) (VEH-MAN-29 to 31) |
| A car parked for months: bringing it back | [car-maintenance-basics.md](car-maintenance-basics.md) (VEH-MAN-36 to 38), [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-52 to 57) |
| What the inspection checks and how to pre-check it at home | [car-maintenance-basics.md](car-maintenance-basics.md) (VEH-MAN-42 to 46), [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-58, 59) |
| Counterfeit parts (*truchos*), choosing a workshop, used oil | [car-maintenance-basics.md](car-maintenance-basics.md) (VEH-MAN-6, 39 to 41) |
| Gol: reading the chassis and engine numbers, year and origin, which version | [vw-gol-1994-specs.md](vw-gol-1994-specs.md) (VEH-GOL-2 to 10) |
| Gol: which oil, coolant and brake fluid, how much; tyre pressure, wheel-bolt torque | [vw-gol-1994-specs.md](vw-gol-1994-specs.md) (VEH-GOL-18 to 26) |
| Gol: carburettor and idle data, adjusting idle, CO, float and choke; ignition timing, spark plugs | [vw-gol-1994-specs.md](vw-gol-1994-specs.md) (VEH-GOL-11 to 13), [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-14, 23, 62 to 64) |
| Gol: cylinder-head bolts, valve clearance (mechanical tappets), what is still unconfirmed | [vw-gol-1994-specs.md](vw-gol-1994-specs.md) (VEH-GOL-14, 44, 45, 47) |
| Gol: which fuse, which bulb | [vw-gol-1994-specs.md](vw-gol-1994-specs.md) (VEH-GOL-32 to 35) |
| Gol: service plan for a car used little; timing belt | [vw-gol-1994-specs.md](vw-gol-1994-specs.md) (VEH-GOL-16, 36 to 38), [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-27, 30) |
| Gol: filters, plugs, parts shared with the Senda; manuals and wiring diagrams | [vw-gol-1994-specs.md](vw-gol-1994-specs.md) (VEH-GOL-39 to 43) |
| Gol: hard cold start, stalls at idle, floods (*se ahoga*) | [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-3, 4, 13 to 15, 19) |
| Gol: oil leaks, engine or steering noises | [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-8, 9, 32 to 34, 42, 43) |
| Gol: loose gear lever (*palanca floja*), broken clutch cable | [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-35, 36) |
| Gol: brake pads, bleeding | [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-37 to 39) |
| Gol: what I can do myself and what needs a mechanic | [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) (VEH-GRP-60, 61) |

The one-line list of every rule is [RULES.md](RULES.md) (generated). The Spanish words people use and the English the
guide uses for them are in [GLOSSARY.md](GLOSSARY.md).

## Documents
| File | Prefix | Status | Covers |
|---|---|---|---|
| [traffic-law.md](traffic-law.md) | VEH-LEY | draft | Ley 24.449 and its regulation after Decreto 196/2025, PBA and CABA: licence classes, documents to carry, digital documents, equipment, lights, speed, alcohol, priority, overtaking, children, phones, parking, police checks, accidents |
| [road-signs.md](road-signs.md) | VEH-SEN | draft | The new Anexo L: regulatory, warning, informative and roadwork signs, markings, traffic lights, level crossings, flaggers, CABA specifics, poor or missing signage and fines |
| [fines-and-points.md](fines-and-points.md) | VEH-MUL | draft | The UF, where to check, voluntary payment, defence and hearings, pay-or-dispute calculation, payment plans, prescription, camera tickets, the points licence, renewal, buying and selling, scams (moved from the budget library's traffic-fines page, re-verified) |
| [tolls-and-telepase.md](tolls-and-telepase.md) | VEH-PEA | draft | TelePASE: getting, paying, failures, cancelling; free-flow highways in the AMBA; passing without a tag; national routes and the 2026 deadline; neighbouring countries |
| [insurance.md](insurance.md) | VEH-SEG | draft | Mandatory cover, Ley 17.418, cover types, reading and comparing a policy, SSN, accidents and claims, CLEAS, the Mercosur certificate, old cars, a car that does not circulate, cancelling (moved from the budget library's car-ownership page) |
| [ownership-and-paperwork.md](ownership-and-paperwork.md) | VEH-DOC | draft | Registry (DNRPA), vehicle cards and title, buying, selling and the sale report, addresses, vehicle tax, VTV and RTO, the licence, lost documents, classic vehicles, an owner checklist |
| [trip-preparation.md](trip-preparation.md) | VEH-VIA | draft | Pre-trip check, documents and equipment, planning, driving technique (gravel, wind, fog, night, mountains), old cars on long trips, breakdowns and accidents on the road, border crossings, fuel, a printable checklist |
| [car-maintenance-basics.md](car-maintenance-basics.md) | VEH-MAN | draft | Working safely, routine checks and intervals, warning lights, diagnosis by symptom, battery, lights, brakes, a car parked for months, workshops and parts, pre-checking the inspection |
| [vw-gol-1994-specs.md](vw-gol-1994-specs.md) | VEH-GOL | draft | First-generation VW Gol: identification (VIN, engine codes, versions, origin), engines, carburettor and ignition data, capacities, torques, chassis, electrical (fuses, relays, bulbs), maintenance plan, parts, manuals, source conflicts |
| [vw-gol-1994-repairs.md](vw-gol-1994-repairs.md) | VEH-GRP | draft | First-generation VW Gol: diagnosis by symptom, carburettor, ignition, cooling, timing belt and engine, clutch and linkage, brakes, suspension and steering, electrical, body, reviving after a year parked, emissions and the inspection, owner or mechanic |

"Draft" means written and checked for shape on 2026-11-15, with the unconfirmed points marked in each rule; nothing here
has been reviewed by a lawyer, an insurer or a mechanic yet.

## Offline helper (`gateway vehiculos`)
- `gateway vehiculos search WORD [WORD...]`: rules whose title has the words (English, or Spanish through GLOSSARY.md).
- `gateway vehiculos rule VEH-MUL-10 [...]`: prints only that rule.
- `gateway vehiculos fine --uf 300 --uf-value 2340 [--uf-later X] [--p-win 0.6]`: a fine in UF, the voluntary-payment amount
  and the chance of winning above which a defence pays (VEH-MUL-17). `--amount PESOS` turns a printed amount back into UF.
- `gateway vehiculos trip --km 1200 --consumption 8,5 --tank 47 [--price P] [--longest-gap KM] [--toll X ...]`: litres, cost,
  range on one tank with a reserve, refuels, and whether the longest stretch without a station fits (VEH-VIA-16).

## How to extend it
Add a rule at the end of its document with the next number and the six fields; a new topic is a new document with its own
three-letter prefix, listed in the tables above. Then run `python3 aibridge/vehiculos_guide_selftest.py --write-index` (it
rebuilds RULES.md and checks front matter, fields, numbering, cited IDs, links, the glossary and that nothing personal is in
the folder: no plates, VINs, names, phones or mails; worked examples use invented data). Downloaded manuals and decrees used
as sources stay outside the repository, cited by title and page.
