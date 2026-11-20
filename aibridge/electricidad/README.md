---
title: Electrical guide for construction work in Argentina (index)
scope: low-voltage electrical installations in Argentina (houses, apartments and condominium buildings (*propiedad horizontal*), offices and small shops, construction sites and site compounds); the knowledge base of the bridgeai `electricidad` pack
when_to_use: start here for any electrical question; find the document for the situation and cite the rule by its ID
related: [regulations-and-permits.md, grades-and-circuits.md, conductors-and-conduits.md, current-ratings-and-devices.md, protection.md, earthing.md, panels.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md, surveys-and-drawings.md, teamwork-and-rehabilitation.md, manufacturers-and-materials.md, iram-standards.md]
as_of: 2026-11-15
sources: [AEA 90364-7-771 Ed. 2006 + corrigenda, AEA 90364-7-770 Ed. 2017 + Corrigendum 1 (2018) (Ed. 2026 digital on sale and print on pre-sale), AEA 90364-7-772 Ed. 2019, AEA 90364-6 Ed. 2025, Ley 19.587 with Dec. 351/79 and Dec. 911/96, Res. SRT 900/2015, Res. ENRE 225/2011 and 269/2012 (now ENReGE), Res. SIyC 236/2024 (Anexo II as per Res. SIyC 26/2025) + Disp. DNRT 2/2025]
---
# Electrical guide

Reusable knowledge for electricians, installers, construction technicians (*maestros mayores de obra*) and anyone taking on
a job in Argentina: rules from the AEA wiring regulations and national law, common cases, procedures, safety and
calculations. The agent of the `electricidad` pack reads it in `/usr/local/share/aibridge/electricidad/` and cites each
rule by its ID ("does not comply with ELEC-PRO-7"). It is written in a fixed form so that a person or an assistant quickly
finds the rule that applies.

**Example case that runs through the guide:** a building with ground floor + 4 floors of single-phase apartments
(*deptos*) (collective three-phase supply) and an existing panel (*tablero*) reviewed from a photo. Demand, phase
balancing, riser (*montante*) and common services (*servicios generales*): [buildings.md](buildings.md) ("Example case");
single-line diagram (*unifilar*) of an apartment's panel: [panels.md](panels.md) ELEC-TAB-18; the panel in the photo:
[reviewing-a-panel.md](reviewing-a-panel.md) (worked example) and ELEC-TAB-26; an example survey (*relevamiento*) in
`examples/house-panel-photo.json`.

**Full walkthrough of the case, with drawings and calculations:** [examples/README.md](examples/README.md). It includes
the building as a survey (`examples/building-4-floors.json`, with apartment 4A complete) and its floor plans, single-line
diagrams, work sheet and DXF in `examples/output-building/`.

## Find the document for your situation
| Situation | Read |
|---|---|
| Which norm or edition applies, who can sign, license (*matrícula*), professional council (*colegio*) | [regulations-and-permits.md](regulations-and-permits.md) (ELEC-NOR-1 to 4, 8, 12) |
| Requesting a new meter (*medidor*): DCI (installation conformity declaration) in the Edenor/Edesur area, certificate in Córdoba, other provinces | [regulations-and-permits.md](regulations-and-permits.md) (ELEC-NOR-9, 10, 13) |
| Meter pillar (*pilar*) or construction supply (*luz de obra*), site safety file (*legajo de seguridad*), SRT earthing test report (*protocolo de tierra*) | [regulations-and-permits.md](regulations-and-permits.md) (ELEC-NOR-5, 7, 11, 21), [site-safety.md](site-safety.md) (ELEC-SEG-14, 34) |
| Buying material: certification, conformity marking, counterfeits (*truchos*) | [manufacturers-and-materials.md](manufacturers-and-materials.md) (ELEC-FAB-1 to 3, 12), [iram-standards.md](iram-standards.md) (ELEC-IRA-1 to 4), ELEC-NOR-14 |
| What an IRAM standard says, whether it is current or withdrawn (*anulada*) | [iram-standards.md](iram-standards.md) (ELEC-IRA-19) |
| 770 or 771? Electrification grade (*grado de electrificación*), number of circuits, outlet points (*bocas*) | [grades-and-circuits.md](grades-and-circuits.md) (ELEC-CIR-1 to 7) |
| Demand (DPMS, maximum simultaneous power demand), single-phase or three-phase, phase balancing | [grades-and-circuits.md](grades-and-circuits.md) (ELEC-CIR-12 to 16) |
| Adding an air conditioner (*aire*), a water heater (*termotanque*), a cooker (*cocina*) or a charger to what already exists | [grades-and-circuits.md](grades-and-circuits.md) (ELEC-CIR-25), [special-installations.md](special-installations.md) (ELEC-ESP-39), [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-21 to 23) |
| Cable cross-section (*sección*), voltage drop (*caída de tensión*), colors, conduits (*cañerías*) and boxes | [conductors-and-conduits.md](conductors-and-conduits.md) (ELEC-CON-5 to 14) |
| How much current a cable, a socket outlet (*toma*), a power strip (*zapatilla*), a busbar comb (*peine*) or a terminal (*borne*) can carry | [current-ratings-and-devices.md](current-ratings-and-devices.md) (ELEC-AMP-1 to 9, 19 to 23) |
| Choosing an MCB (*térmica*), RCD (*diferencial*), SPD (*DPS*), voltage protector (*protector de tensión*); selectivity (discrimination) | [protection.md](protection.md) (ELEC-PRO-1 to 21) |
| Earthing (*puesta a tierra*): earth rod (*jabalina*), Ra value, measurement, PE, equipotential bonding | [earthing.md](earthing.md) (ELEC-PAT-1 to 13) |
| Building a panel: enclosure (*gabinete*), minimum contents, assembly, single-line diagram | [panels.md](panels.md) (ELEC-TAB-1 to 19) |
| Reviewing an existing panel, in person or from a photo | [reviewing-a-panel.md](reviewing-a-panel.md) (ELEC-REV-1 to 3, 21, 22) |
| Condominium building (*PH*, *propiedad horizontal*): supply feasibility (*factibilidad*), meter room, risers, common services | [buildings.md](buildings.md) (ELEC-EDI-1 to 12, 26), [panels.md](panels.md) (ELEC-TAB-20, 23) |
| Elevator, pumps, emergency systems, garages (*cocheras*) with EV charging, power factor of the owners' association (*consorcio*) | [buildings.md](buildings.md) (ELEC-EDI-13 to 22) |
| Working safely: five golden rules, lockout (*bloqueo*), PPE (*EPP*), instruments | [site-safety.md](site-safety.md) (ELEC-SEG-1 to 13) |
| Electrical accident, fire in a panel, storm | [site-safety.md](site-safety.md) (ELEC-SEG-23, 24, 26, 31) |
| Tests before energizing, test report (*protocolo*), handover of the job | [testing-and-commissioning.md](testing-and-commissioning.md) (ELEC-MED-1 to 12) |
| "Salta el disyuntor" ("the RCD (*disyuntor*) trips"), "salta la térmica" ("the MCB trips"), socket outlets that heat up, voltage too low (undervoltage) | [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-1 to 13) |
| "¿Pongo una térmica más grande?" ("Do I put in a bigger MCB?"), "¿puenteo el disyuntor hasta el lunes?" ("Do I bypass the RCD until Monday?") | [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-34) |
| Broken neutral (*corte de neutro*) in a building, appliances burned out in several apartments | [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-14), [buildings.md](buildings.md) (ELEC-EDI-11), [protection.md](protection.md) (ELEC-PRO-19) |
| Bathroom, swimming pool, air conditioning, kitchen, motors and pumps | [special-installations.md](special-installations.md) (ELEC-ESP-3 to 16) |
| Electric vehicle, solar panels, generator set (*grupo electrógeno*), UPS | [special-installations.md](special-installations.md) (ELEC-ESP-17 to 27), [earthing.md](earthing.md) (ELEC-PAT-21) |
| Installation without drawings: survey it and draw the plan (*plano*) | [surveys-and-drawings.md](surveys-and-drawings.md) (ELEC-PLA-6 to 17) |
| Rehabilitating an installation with leakage (*fugas*) and short circuits with a crew (*cuadrilla*); group lockout | [teamwork-and-rehabilitation.md](teamwork-and-rehabilitation.md) (ELEC-EQU-1 to 11, 20 to 26) |
| Old installation: fuses, knife switches (*cuchillas*), cloth-insulated cables (*cables de tela*), no earth | [reviewing-a-panel.md](reviewing-a-panel.md) (ELEC-REV-23), [troubleshooting-common-cases.md](troubleshooting-common-cases.md) (ELEC-DIA-17), [earthing.md](earthing.md) (ELEC-PAT-23) |

## Documents
| File | Prefix | Status | Covers |
|---|---|---|---|
| [regulations-and-permits.md](regulations-and-permits.md) | ELEC-NOR | ready | Legal framework: mandatory AEA, current editions, professional scope (*incumbencias*), DCI (ENRE area, now ENReGE), Córdoba, other provinces, materials, periodic inspections, electro-dependent users (*electrodependientes*), distributed generation |
| [grades-and-circuits.md](grades-and-circuits.md) | ELEC-CIR | ready | 770 or 771, floor area, grades, minimum circuits, outlet points, conventional loads, DPMS, total load, phase balancing, worked examples |
| [conductors-and-conduits.md](conductors-and-conduits.md) | ELEC-CON | ready | Cables, minimum cross-sections, PE, colors, current-carrying capacity, voltage drop, conduits, boxes, cable trays, underground, splices, risers, short circuit |
| [current-ratings-and-devices.md](current-ratings-and-devices.md) | ELEC-AMP | ready | Current-carrying capacity tables by installation method, correction factors, ratings, breaking capacity, RCDs, socket outlets, power strips, terminals, busbar combs, fuses, contactors |
| [protection.md](protection.md) | ELEC-PRO | ready | MCBs, RCDs, main switch, neutral, SPD, voltage protector, fuses, selectivity, AFDD, motors, generator set |
| [earthing.md](earthing.md) | ELEC-PAT | ready | TT system, earth rods, Ra and its measurement, PE, equipotential bonding, buildings, lightning protection (*pararrayos*), SRT test report, maintenance |
| [panels.md](panels.md) | ELEC-TAB | ready | Main panel, sub-panels (*tableros seccionales*), common services and construction site panels: location, enclosure, contents, assembly, single-line diagram, thermal calculation, final check |
| [buildings.md](buildings.md) | ELEC-EDI | ready | Condominium buildings: supply feasibility, transformer substation (*centro de transformación*), meter room (*sala de medidores*), risers, phases, broken neutral, common services, example case ground floor + 4 |
| [site-safety.md](site-safety.md) | ELEC-SEG | ready | Five golden rules, lockout, verifying absence of voltage, clearances, PPE, instruments, construction site panel, work at height, emergencies |
| [testing-and-commissioning.md](testing-and-commissioning.md) | ELEC-MED | ready | Inspection, continuity, insulation, earth, RCD testing, polarity, voltage, loop impedance, SRT test report, handover, thermography |
| [troubleshooting-common-cases.md](troubleshooting-common-cases.md) | ELEC-DIA | ready | ID (RCD) and MCB tripping, leakage, neutrals, loose connections, voltage out of tolerance, broken neutral, added loads, construction site cases |
| [special-installations.md](special-installations.md) | ELEC-ESP | ready | Bathrooms, pools, AC, kitchen, household appliances, motors and pumps, electric vehicle, photovoltaics, generator sets and UPS, outdoor areas, electric fence |
| [reviewing-a-panel.md](reviewing-a-panel.md) | ELEC-REV | ready | Review of an existing panel (in person or from a photo): what you see, what you deduce, findings by severity, report, worked example |
| [surveys-and-drawings.md](surveys-and-drawings.md) | ELEC-PLA | ready | Surveying an installation without drawings, identifying circuits, `survey.json`, drawings, per-circuit sheets, as-built (*conforme a obra*) |
| [teamwork-and-rehabilitation.md](teamwork-and-rehabilitation.md) | ELEC-EQU | ready | Diagnosis and sectioning of an installation with leakage, crew organization, group lockout, energizing in stages |
| [manufacturers-and-materials.md](manufacturers-and-materials.md) | ELEC-FAB | ready | Brands and product lines in Argentina, published data, how to buy, how to spot counterfeit material, complaints |
| [iram-standards.md](iram-standards.md) | ELEC-IRA | ready | Annotated catalog of LV IRAM standards: current, withdrawn, what to require printed on each product |

## Offline calculator (`gateway electricidad`)
The agent does not calculate from memory: it uses the calculator (`aibridge/electricidad.py`, installed as
`/usr/local/bin/electricidad`) and shows the calculations. Each result comes with findings with `check`, `rule` (clause),
`status` (`ok`, `warn`, `fail`, `unknown`) and `evidence`; `unknown` marks a value not verified in a primary source and is
never shown as ok. With `--json` the output is for machines. Exit codes: 0 everything complies, 1 something does not
comply, 2 invalid input.

| Subcommand | What for | Example |
|---|---|---|
| `current` | Power ↔ current, single-phase or three-phase | `gateway electricidad current --power 7000 --va` |
| `drop` | Voltage drop of a run and its limit (final circuit, sub-main, motor, main line) | `gateway electricidad drop --current 31.8 --length 20 --section 16 --line submain --pf 0.9` |
| `size` | Minimum cross-section by current-carrying capacity, voltage drop and regulatory minimum, with the suggested MCB (*PIA*) | `gateway electricidad size --current 31.8 --length 20 --circuit submain` |
| `coordinate` | Ib ≤ In ≤ Iz and I2 ≤ 1.45 Iz (MCB or gG fuse) | `gateway electricidad coordinate --ib 14 --in 16 --section 2.5 --grouped 2` |
| `demand` | Electrification grade, DPMS and minimum circuits (770 or 771) | `gateway electricidad demand --area 58 --iug 7 --tug 6 --tug 4 --norm 771` |
| `earth` | Ra × IΔn ≤ 24 V, Ra ≤ 40 Ω and recommended Ra | `gateway electricidad earth --ra 18 --idn 30` |
| `tables` | The internal tables with their source, date and whether they are verified | `gateway electricidad tables f_temperature` |

- An apartment, an office or a shop uses `--norm 771`; the 770 (default in `demand`) is for the single-family
  house.
- It has no short-circuit or earth rod resistance subcommands (yet): those calculations are worked by hand in
  [protection.md](protection.md) (ELEC-PRO-3) and [earthing.md](earthing.md) (ELEC-PAT-4, 13).
- Selftest: `python3 -I aibridge/electricidad_selftest.py`.
- Surveys and drawings: `electricidad-plan` (`aibridge/electricidad_plan.py`, installed as
  `/usr/local/bin/electricidad-plan`) with `new`, `validate`, `draw`, `single-line`, `sheets`, `dxf`, `status`,
  `summary` and `symbols`; the JSON contract (`survey.json`) is in [surveys-and-drawings.md](surveys-and-drawings.md).
  From the gateway: `gateway electricidad plan ...` (the calculator passes it through whole). Selftest:
  `python3 -I aibridge/electricidad_plan_selftest.py`.

## Rule index
[RULES.md](RULES.md) has one line per rule (ID and title), generated by `electricidad_guide_selftest.py --write-index`.
To find which rule applies, grep it there; then read only that rule in its document
(`grep -n '^### ELEC-PRO-7' *.md`). The documents are long: don't read them whole.

## Glossary
[GLOSSARY.md](GLOSSARY.md) maps the Argentine words people use (*térmica*, *disyuntor*, *jabalina*, *pilar*...) to the
English term each rule uses. The guide is in English; answer in the person's language and, in Spanish, with the Argentine
word. `gateway electricidad search disyuntor` looks a Spanish word up there before searching the rule index.

## Criteria shared by the whole guide
So that two documents don't give different answers, these criteria apply in all of them (consistency review of
2026-11-15):
- **Apartment in a building = AEA 90364-7-771**; the 770 only for the single-family house within its scope (63 A,
  10 kA, BA2/BD1), or for an apartment if the authority accepts it in writing (ELEC-CIR-1, ELEC-EDI-26, ELEC-CON-24).
  Common services and the building as a whole: 772.
- **Voltage drop in the sub-main ≤ 1 %**: mandatory in the 771, recommended in the 770; final circuit ≤ 3 % in total (ELEC-CON-9).
- **Values of the 770 = Ed. 2017 + Corrigendum 1 (2018).** Ed. 2026 is already sold in digital form (print on pre-sale,
  delivery announced from 2026-11-16) and has no published date of entry into force; its text has not been read (ELEC-NOR-4).
- **Earthing in TT:** Ra ≤ 40 Ω with ID (RCD) ≤ 300 mA, limit voltage 24 V; every final circuit with a non-delayed 30 mA ID
  (ELEC-PAT-9, ELEC-PRO-7).
- **Instruments for measuring live:** CAT III 600 V or CAT IV 300 V as a minimum; CAT IV at the meter pillar, meter and
  incoming side of the main panel (ELEC-SEG-13).
- **Voltage tolerance in the Edenor/Edesur area:** ±8 % (202.4 to 237.6 V), Subanexo 4 of the 2025-2030 period
  (ELEC-DIA-13).
- **Regulator of the Edenor/Edesur area:** the ENRE became the ENReGE (acronym from argentina.gob.ar/enre, consulted 2026-11-15, and from the body's resolutions in
  the Boletín Oficial (official gazette); "ENRGE", which appears in the press, is the same body: the guide always writes ENReGE);
  Edelap has been under OCEBA since 2011 (ELEC-NOR-13, ELEC-NOR-18).
- **MCBs (*termomagnéticas*) and RCDs:** IEC 60898-1, 61008-1 and 61009-1; IRAM 2169 and 2301 are withdrawn
  (ELEC-IRA-7).

## What goes here and what doesn't
- **Here (shared):** rules with their source, procedures, worked calculations with example numbers, checklists,
  decision criteria, anonymized cases ("Real case:" on one line, with nobody's data).
- **Does not go here:** client data (names, addresses, phone numbers, DNI national ID numbers), surveys of real jobs, photos of
  third parties' panels, quotes and **prices** (they change every month). Surveys go in the person's working
  directory (`/workdir/electricidad`), not in git.
- **Never:** full text or tables of AEA or IRAM standards (they are paid and copyrighted): summarize and cite the clause
  ("see table 771.16.I"); a single widely published value is fine, with its source. Nor instructions for live
  work.

## Conventions (for people and assistants)
- Every document starts with YAML front matter: `title`, `scope`, `when_to_use`, `related`, `as_of`, `sources`.
- Rules have a stable ID with their document's prefix (`ELEC-NOR-n`, `ELEC-PRO-n`, ...). They are not renumbered: a
  new rule takes the next number even if it sits in the middle of the document, and a rule that is withdrawn is marked
  **Retired** with the date and the rule that replaces it.
- Every rule always has the same fields: **Rule**, **Why**, **How**, **Verify**, **Don't**, **Source**.
- **Source** = norm + clause or article + edition or year, or the link. Whatever could not be confirmed in the primary
  source is marked **"Not verified in a primary source:"** with what is known and where it comes from.
- Numeric values always with unit and source; formulas with a worked example. Dangerous steps say so.
- `as_of` is the date on which the document's regulations were reviewed. The regulations (AEA editions, ENReGE, SRT and
  Industria y Comercio (Industry and Trade) resolutions, utility regulations) are reviewed **at least once a year**, and
  sooner if a new edition comes out (for example, when the 770 Ed. 2026 is read). When a value changes, it is changed in
  all documents and in `electricidad.py` (with its selftest), and the commit message says what changed.
- Assistants: cite the ID of the rule you apply and its source; if a value is marked as not verified, say so; if the
  guide and the situation don't match, stop and ask instead of improvising. Nothing in this guide authorizes live
  work.

## What this guide does not replace
The design, the technical direction (*dirección técnica*), the DCI or the certificate and the signature are done by a
qualified professional or installer with professional scope in that jurisdiction. The utility (*distribuidora*) decides on
the service connection (*acometida*), the meter and the power; the municipality and the local regulator or professional
council decide on drawings, approvals and inspections. When in doubt about safety: switch off, lock out and ask.
