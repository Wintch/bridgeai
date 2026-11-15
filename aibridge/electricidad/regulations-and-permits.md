---
title: Regulations and permits (legal framework for electrical installations in Argentina)
scope: laws, decrees, resolutions and wiring regulations that govern a low-voltage electrical installation in Argentina; who may design, install and sign; what is filed with the utility (DCI, certificate of a compliant installation); mandatory certification of materials; responsibilities of each party
when_to_use: before designing or quoting a job; when you need to request a new meter, a construction meter pillar or a power increase; when someone asks "¿quién me firma esto?" (who signs this for me?), "¿qué norma aplica?" (which standard applies?) or "¿este material es legal?" (is this material legal?); when you need to cite the correct standard in a report
related: [README.md, grades-and-circuits.md, conductors-and-conduits.md, protection.md, earthing.md, panels.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, special-installations.md, reviewing-a-panel.md]
as_of: 2026-11-15
sources:
  - "Ley 19.587 (1972) de Higiene y Seguridad en el Trabajo (occupational health and safety law); Decreto 351/79, ch. 14 and Anexo VI; Decreto 911/96 (construction), arts. 74 to 87"
  - "Res. SRT 900/2015 (earthing and continuity protocol) and its SRT practical guide; Res. SRT 3068/2014 (live work up to 1 kV, adopts AEA 95705 ed. 2013); Res. SRT 11/2022 (BO 2022-03-03; approves the AEA regulation for live work > 1 kV, Comisión 21, ed. 2020 = AEA 95702; repeals Res. SRT 592/2004); Res. SRT 51/97, 35/98, 319/99 (safety program and site file)"
  - "AEA, catalog of printed regulations and Addenda & Corrigenda page (consulted 2026-11-15): 90364 parts 0 to 3 ed. 2025; 90364-4 ed. 2006; 90364-5 ed. 2006; 90364-6 ed. 2025 + corrigenda 1 (06/2025) and 2 (05/2026); 90364-7-771 ed. 2006 + corrigenda 1 to 6 (latest 04/2017); 90364-7-770 ed. 2017 (+ Corrigendum 1, 2018) and ed. 2026 (digital on sale; printed on pre-sale, deliveries from 2026-11-16); 90364-7-772 ed. 2019; 90364-7-704 ed. 2026"
  - "ENRE Res. 225/2011 (Reglamento para la conexión de nuevos suministros, rules for connecting new supplies, 2022 edition text), Res. 269/2012 (DCI form), Res. 380/2015 (construction meter pillar); Reglamento de Suministro ENRE (supply regulation, text per Res. 524/2017 and 525/2017); ENRE area = Edenor and Edesur (Edelap: provincial regulator OCEBA)"
  - "Córdoba: Ley 10.281 (2015) de Seguridad Eléctrica (electrical safety law), Decreto 1022/2015, ERSeP general resolutions (RG 96/2025)"
  - "COPIME Res. 95/2026 (BO 2026-05-11), qualified persons (idóneos) and issuing of DCI"
  - "Secretaría de Industria y Comercio: Res. 236/2024 (Anexo II replaced by Res. 26/2025) and 237/2024; Disposición DNRT 2/2025 (materials for electrical installations); Res. 16/2025 (repeals Res. 169/2018); Providencia DNRT PV-2025-120654504 (conformity marking, 2025-10-30)"
  - "Decreto 452/2025 (Ente Nacional Regulador del Gas y la Electricidad); argentina.gob.ar/enre (ENReGE takes over functions from May 2026)"
  - "Ley 27.424 (distributed generation), Decreto 986/2018 and Res. ex-SGE 314/2018 (details in special-installations.md); Ley 27.351 (electro-dependent persons)"
---
# Regulations and permits

Which standards govern an electrical installation in Argentina, in what order they apply, who may sign
what, and what paperwork the utility (distribution company, *distribuidora*) asks for before connecting power. Each rule has an ID (`ELEC-NOR-n`) so that a
review, a quote or the agent can cite it ("no cumple ELEC-NOR-10": "does not comply with" that rule).

The golden rule: **in Argentina there is no single standard**. There is a national layer (occupational safety, trade,
electricity regulator), a technical layer (AEA Reglamentación, the wiring regulations), a provincial layer (electrical safety laws
where they exist, professional councils) and a municipal and utility layer. The installation has to
comply with all of them at once. Design recommendation (not a legal rule): if two technical requirements can be
compared and both met, adopt the stricter one. If they contradict each other (both cannot be met),
the deciding factor is not "the stricter one" but the competent authority of that jurisdiction for that subject matter (ENRE itself
gives priority "en primera instancia" (in the first instance) to local regulations, ELEC-NOR-1): ask for the answer in writing.

> AEA and IRAM standards are paid and copyrighted. This guide summarizes and cites clauses; it does not replace
> having the current edition in hand.

## Quick reference: which standard to check for what

| Situation | Main standard | Where it is in this guide |
|---|---|---|
| Designing the installation of a dwelling, office or single shop | AEA 90364-7-771 (ed. 2006) + parts 0 to 6 | ELEC-NOR-2, 3; [grades-and-circuits.md](grades-and-circuits.md) |
| Small single-family house (up to 63 A, prospective Icc up to 10 kA, BA2/BD1) | AEA 90364-7-770 ed. 2017 + Corrigendum 1 (2018); ed. 2026 is sold in digital form and the printed one is on pre-sale (no published effective date) | ELEC-NOR-3, 4 |
| Common areas and common services of a building (condominium building, *propiedad horizontal*, PH) | AEA 90364-7-772 (ed. 2019) | ELEC-NOR-3; [buildings.md](buildings.md) |
| Bathrooms, pools, public assembly venues, electric vehicles, photovoltaics, elevators | AEA 90364-7-701, 702, 718, 722, 712, 791 | ELEC-NOR-3; [special-installations.md](special-installations.md) |
| Construction site electrical installation (site compound, construction supply) | Dec. 911/96 arts. 74-87 + AEA 90364-7-704 (ed. 2026) or, where it has not yet been adopted, annex 771-B.7 of the 771 | ELEC-NOR-5; [site-safety.md](site-safety.md) |
| Occupational safety on the site (program, file, health and safety service) | Ley 19.587, Dec. 911/96, Res. SRT 51/97, 35/98, 319/99 | ELEC-NOR-21; [site-safety.md](site-safety.md) |
| How work is done (dead work, lockout/tagout, distances) | Dec. 351/79 Anexo VI; Dec. 911/96 arts. 75-82 (on construction sites) | ELEC-NOR-6 |
| Live work (only personnel authorized by the company) | Res. SRT 3068/2014 (≤ 1 kV, AEA 95705 ed. 2013); Res. SRT 11/2022 (> 1 kV, AEA regulation Comisión 21 ed. 2020 = AEA 95702) | ELEC-NOR-6 |
| Annual earthing and continuity measurement at a workplace | Res. SRT 900/2015 | ELEC-NOR-7; [testing-and-commissioning.md](testing-and-commissioning.md) |
| New single-phase T1R meter in the Edenor/Edesur area (ENRE area) | Res. ENRE 225/2011 + 269/2012 (DCI, installation conformity declaration) | ELEC-NOR-10 |
| Three-phase, T1G, T2, T3 meter in that area | Res. ENRE 225/2011 section III (municipal approval or start-of-works permit + DCI) | ELEC-NOR-10 |
| Construction meter pillar in that area | Res. ENRE 380/2015 (DCI for construction meter pillar) | ELEC-NOR-11 |
| New meter in La Plata and the Edelap area | Edelap requirements; provincial regulator OCEBA (not ENRE) | ELEC-NOR-13 |
| New supply in Córdoba | Ley 10.281 + Dec. 1022/2015 + ERSeP (Certificado de Instalación Eléctrica Apta, certificate of a compliant electrical installation) | ELEC-NOR-9 |
| Who may sign? | Scope of the professional degree (incumbencia) + license (*matrícula*) with the professional council of the jurisdiction | ELEC-NOR-8, 12 |
| Is this MCB (*térmico*) / RCD (*disyuntor*) / cable / socket outlet legal? | Res. SIyC 236/2024 (Anexo II per Res. SIyC 26/2025) + Disp. DNRT 2/2025 + conformity marking | ELEC-NOR-14 |
| Where does the utility's part end and mine begin? | Reglamento de Suministro ENRE (chapter on user obligations) | ELEC-NOR-15 |
| Earthing: definitions and measurements | AEA 95501 / IRAM 2281 (parts 1 to 4 and 8) | [earthing.md](earthing.md) |
| Short-circuit calculation | AEA IEC 60909-0 (ed. 2021) and AEA 90909-1 (calculation factors, ed. 2005) | [protection.md](protection.md) |
| User-generator (panels that feed into the grid) | Ley 27.424, Dec. 986/2018, Res. ex-SGE 314/2018 and amendments; AEA 90364-7-712 | ELEC-NOR-22; [special-installations.md](special-installations.md) |
| Lightning protection | AEA 92305 / IRAM 2184 | [special-installations.md](special-installations.md) |
| Outdoor lines, service connections, transformer substations | AEA 95101, 95150, 95201, 95301, 95401, 95403 | ELEC-NOR-4 |

## Current editions (AEA catalog as of 2026-11-15)

Taken from the AEA catalog of printed regulations (aea.org.ar/reglamentaciones/impresas), consulted
on 2026-11-15, and from the "Addenda & Corrigenda" page (aea.org.ar/addenda-corrigenda). AEA does not always publish
what changed between editions; when we could not confirm it, we say so.

> **Effective date:** AEA does not publish an effective date for the 2025 and 2026 editions (the announcements of
> parts 0 to 3, Part 6 and 7-704 do not state one). The utility or the jurisdiction may keep
> requiring the previous edition: for example, the ENRE DCI form cites the AEA "vigente (versión 2006)" (current, 2006 version).
> As of 2026-11-15 we could not confirm whether any jurisdiction or utility has expressly adopted a 2025/2026
> edition. Write down in the technical report which edition you used and why (ELEC-NOR-4).

| Document | Short title | Edition | Notes |
|---|---|---|---|
| AEA 90364 parts 0 to 3 | Application guide, scope, definitions, general characteristics | 2025 | First time in a single volume. Updates earthing arrangements (ECT) and the selection of materials according to external influences; documents cited by the regulation become mandatory (AEA announcement "Nueva edición AEA 90364 partes 0 a 3") |
| AEA 90364-4 | Protection for safety | 2006 | |
| AEA 90364-5 | Selection and erection of materials | 2006 | Chapter 57 (stationary batteries) ed. 2026 |
| AEA 90364-6 | Verification of electrical installations (initial and periodic) | 2025 | 3rd edition (Biblioteca SRT catalog); corrigenda 1 (Jun 2025) and 2 (May 2026) |
| AEA 90364-7-701 | Bathrooms and rooms with showers/bathtubs | 2012 | |
| AEA 90364-7-702 | Swimming pools and fountains | 2018 | |
| AEA 90364-7-704 | Construction sites, works, demolitions, site compounds | 2026 | Content not verified. Before, construction site requirements were in annex 771-B.7 of the 771 ed. 2006, which is the one applied by the SRT guide for Res. 900/2015 |
| AEA 90364-7-710 | Medical locations | 2024 | |
| AEA 90364-7-712 | Photovoltaics | 2015 | |
| AEA 90364-7-718 | Public assembly venues | 2008 | |
| AEA 90364-7-722 | Electric vehicles | 2024 | |
| AEA 90364-7-770 | Single-family houses ≤ 63 A, Icc ≤ 10 kA (BA2, BD1) | 2017 | The one used on site today (in force since 2017-09-01, according to panels.md) with its Corrigendum 1 (Aug 2018). No longer listed in the printed catalog |
| AEA 90364-7-770 | Same | 2026 | **Digital on sale; printed on pre-sale** (AEA announces deliveries from 2026-11-16). It has not published an effective date or a transition period. It will replace ed. 2017 when it comes into force in each jurisdiction |
| AEA 90364-7-771 | Dwellings, offices and shops (single units) | 2006 | Still the current one; it replaced the 2002 one and the 1987 general regulation. Corrigenda 1 (Jan 2007), 2 (Jun 2007), 3 (Jan 2008), 4 (Jun 2015), 5 (Feb 2016) and 6 (Apr 2017) |
| AEA 90364-7-772 | Common areas and common services | 2019 | |
| AEA 90364-7-791 T1 / T2 | Elevators / escalators, goods lifts | 2018 / 2020 | |
| AEA 90364-8-1 / 8-82 | Energy efficiency / LV prosumers | 2019 / 2025 | |
| AEA 95150 | LV supply and metering | 2007 | |
| AEA 95201 | Outdoor LV overhead lines | 2018 | |
| AEA 95101 | Outdoor underground lines | 2015 | |
| AEA 95401 / 95403 | Transformer substations / buildings from 1 to 36 kV | 2006 / 2018 | |
| AEA 95501-1 / -2 / -3 (IRAM 2281) | Earthing: general / measurements / ≤ 1 kV | 2026 / 2021 / 2024 | |
| AEA 95705 | Live work in LV | 2013 | Adopted by Res. SRT 3068/2014 |
| AEA 95702 | Live work on installations above 1 kV | 2021 (catalog) | Res. SRT 11/2022 approved the 2020 ed. of Comisión 21; the catalog now lists a 2021 ed. If you work in that field, confirm with the SRT which one applies |
| AEA IEC 60909-0 / AEA 90909-1 | Short-circuit currents / calculation factors | 2021 / 2005 | |
| Guía AEA 770 | "Instalaciones eléctricas en viviendas unifamiliares hasta 10 kW" (electrical installations in single-family houses up to 10 kW) | 2018 | Application guide, not a regulation. Its title says 10 kW; the scope of the 770 regulation is defined by the incoming current (≤ 63 A, that is up to ≈ 13.9 kVA single-phase at 220 V and ≈ 41.5 kVA three-phase at 380 V) |

## Rules

### ELEC-NOR-1: Before designing, build the regulatory map for that job
- **Rule:** for each job, write down what applies in each layer: national (Ley 19.587 and decrees, electricity regulator, trade), technical (applicable AEA sections), provincial (electrical safety law if one exists, professional council, provincial regulator), municipal (building code, approval, final inspection of works) and utility (connection requirements, meter pillar (*pilar*), meter). If there are workers on the site, add the occupational safety layer (safety program, file, Health and Safety service: ELEC-NOR-21).
- **Why:** the same dwelling goes through a different process in Córdoba (ERSeP certificate), in the Edenor/Edesur area (ENRE DCI), in La Plata and the Edelap area (Edelap requirements, OCEBA regulator) or in another province (utility and municipal requirements). Finding out when the utility rejects the request costs weeks.
- **How:**
  1. Identify the jurisdiction (province, municipality) and the utility.
  2. Define the use (dwelling, office, shop, condominium building, construction site) and the tariff you will request (single-phase T1R, three-phase, T1G, T2...).
  3. Download from the utility's website its connection requirements and the current meter pillar or cabinet model.
  4. Ask the municipality whether it requires an electrical drawing or a final inspection for that job, and whether a later commercial permit (in CABA, before the AGC) will ask for electrical documentation. **Not verified in a primary source:** what the CABA Código de Edificación (building code, Ley 6100 amended by Ley 6438) currently requires regarding the electrical drawing; ask in writing.
  5. Use the "which standard to check for what" table above and list the AEA sections.
- **Verify:** the job folder has a "marco normativo" (regulatory framework) sheet with the standard, edition and date consulted for each requirement.
- **Don't:** assume that "con cumplir la AEA alcanza" (complying with the AEA is enough). The AEA is technical; who signs, which form and which inspection each party requires are decided by other rules.
- **Source:** ENRE regulation for connecting new supplies (Res. ENRE 225/2011, 2022 ed. text), section III item 3: "en primera instancia" (in the first instance) the technical regulations of the local authorities govern; Córdoba Ley 10.281 art. 5 (certificate as a mandatory condition for supply).

### ELEC-NOR-2: The AEA 90364 Reglamentación is mandatory, not "recommended"
- **Rule:** design and install according to the AEA 90364 Reglamentación in its current edition. Its mandatory status comes through several routes at once: occupational safety, electricity regulator and provincial laws.
- **Why:** whoever signs an installation that does not comply with the AEA faces disciplinary proceedings before their professional council, may have their DCI or certificate rejected by the utility and, if there is an accident, is liable under civil and criminal law. The ART (workers' compensation insurer) does not sanction the professional (it oversees the employer), but if it paid benefits it may claim against a responsible third party (recovery action, acción de repetición; **not verified in a primary source**, consult a lawyer).
- **How:** know the routes that make it mandatory:
  - Decreto 351/79 (regulating Ley 19.587), Anexo VI, item 3.1 "Características constructivas" (construction characteristics): refers to the AEA regulation (cited under its name at the time, "Asociación Argentina de Electrotécnicos").
  - Decreto 911/96 (construction), art. 86: the construction site installation is designed as a permanent one "siguiendo las disposiciones" (following the provisions) of the AEA.
  - Decreto 617/97 (agriculture), art. 18, and Decreto 249/07 (mining), art. 99: compliance with the AEA and, on a supplementary basis, with the electricity regulator's rules.
  - Reglamento de Suministro ENRE, user obligations, subsections c) and d): protection and maintenance downstream of the first isolation point according to the AEA or the local standard.
  - Córdoba: under Ley 10.281, ERSeP issued its "Reglamentación técnica para la ejecución y verificación de instalaciones eléctricas" (technical regulation for the installation and verification of electrical installations), which is based on AEA 90364. **Not verified in a primary source:** the article of Ley 10.281 or Dec. 1022/2015 that refers to the AEA (we did not confirm that the law "adheres" in those words).
- **Verify:** the technical report states "AEA 90364, partes 0 a 6 y sección/es 7-xxx, edición ..." (the general parts, the Part 7 section or sections used, and the edition). Part 7 is not self-contained: what a Part 7 section does not say is resolved by parts 1 to 6.
- **Don't:** cite "la norma AEA" (the AEA standard) without section or edition, or apply only the 771 while forgetting the general parts.
- **Source:** Res. SRT 900/2015, practical interpretation guide (SRT), pp. 1-2, which transcribes Dec. 351/79 Anexo VI ch. 14 item 3.1, Dec. 911/96 art. 86, Dec. 617/97 art. 18 and Dec. 249/07 art. 99; Decreto 911/96 art. 86 (full text verified); Reglamento de Suministro ENRE (text per Res. 524/2017 and 525/2017); Ingeniería Eléctrica, "Todo sobre AEA 90364", Sept. 2024 (Part 7 is not self-contained).
### ELEC-NOR-3: Choose the correct Part 7 section according to the use
- **Rule:** each area of the job is designed with the Part 7 section that applies to it, plus parts 0 to 6.
- **Why:** different rules coexist in the same building: the units (771 or 770), the common services (772), the elevators (791), the bathrooms (701) and the construction supply (704). Using the wrong section leads to wrongly chosen electrification grades, circuits or protection.
- **How:**

  | Area | AEA section |
  |---|---|
  | Apartment (*departamento*), office or single shop | 7-771 |
  | Single-family house with incoming device ≤ 63 A, prospective Icc ≤ 10 kA, BA2/BD1 | 7-770 ed. 2017 (if the designer chooses it and the jurisdiction accepts it; otherwise 7-771) |
  | Landings (*palieres*), shared garages, pumps, caretaker's unit, common lighting | 7-772 |
  | Elevators, goods lifts | 7-791 T1 / T2 |
  | Bathrooms in any unit | 7-701 (in addition to the 771) |
  | Pool, fountain | 7-702 |
  | Site compound (*obrador*), construction supply (*luz de obra*), demolition | 7-704 ed. 2026 or annex 771-B.7 (see ELEC-NOR-5), and Dec. 911/96 |
  | Public assembly venue | 7-718 |
  | Electric vehicle charging | 7-722 |
  | Photovoltaic panels / prosumer | 7-712 and 8-82 |

- **Verify:** the circuit schedule (*planilla*) states, for each panel (distribution board, *tablero*), the AEA section used. In Córdoba, also check that the installer's category covers that use (ELEC-NOR-9).
- **Don't:** design the common services of a building with the 771 "porque es lo que conozco" (because it is what I know), or treat a shop open to the public as a single shop.
- **Source:** AEA catalog of printed regulations (consulted 2026-11-15) for titles and scopes; SRT practical guide for Res. 900/2015, p. 3 (list of applicable sections); the technical details of each section are in [grades-and-circuits.md](grades-and-circuits.md), [buildings.md](buildings.md) and [special-installations.md](special-installations.md).

### ELEC-NOR-4: Work with the current edition and record it; check the catalog before signing
- **Rule:** before closing a design or signing a DCI (installation conformity declaration), confirm in the AEA catalog the current edition of each part you use and record it in the technical report.
- **Why:** between 2024 and 2026 new editions of key parts came out (0 to 3 in 2025, Part 6 in 2025, 7-704 in 2026, 7-710 and 7-722 in 2024), and 7-770 ed. 2026 is already sold in digital form (the printed one, on pre-sale). AEA does not publish an effective date for those editions. The 771, on the other hand, is still on the 2006 edition with its corrigenda. Working from old notes or loose PDFs from the internet is the most common cause of errors of judgment.
- **How:**
  1. Check aea.org.ar (printed and digital regulations, and the "Addenda & Corrigenda" section).
  2. For the 771, verify that you have incorporated the six published corrigenda (1 to 6, the latest from April 2017); for Part 6 ed. 2025, corrigenda 1 (Jun 2025) and 2 (May 2026).
  3. If the jurisdiction or the utility cites a specific edition (for example, the ENRE DCI form mentions the AEA "vigente (versión 2006)" (current, 2006 version)), comply with that one and, if there is a later, stricter one and both can be met, also the later one; if they clash, ask in writing whoever requires it.
  4. If you use a new edition not yet adopted by your jurisdiction, put it in writing.
- **Verify:** the technical report says, for example: "AEA 90364 partes 0-3 ed. 2025, parte 4 ed. 2006, parte 5 ed. 2006, parte 6 ed. 2025 con corrigendas 1 y 2, sección 7-771 ed. 2006 con corrigendas 1 a 6" (that is: each part and section used, with its edition and the corrigenda incorporated).
- **Don't:** copy tables from a pirated PDF or from notes with no edition; tables change between editions and corrigenda (for example, Corrigendum 1 of the 770 ed. 2017, Aug 2018, clause 770.19.5.2.1 and table 770.19.I, aligned the minimum insulation resistance values with IEC 60364-6; see [testing-and-commissioning.md](testing-and-commissioning.md)).
- **Source:** AEA catalog of printed regulations and "Addenda & Corrigenda" page (consulted 2026-11-15); AEA page for 7-771 ("Edición 2006"); AEA announcements "Nueva edición AEA 90364 partes 0 a 3", "AEA 90364-6 nueva edición" and "Nuevo documento AEA 90364-7-704" (no effective date); ENRE T1R DCI form (note 2); Corrigendum 1 of the 770 according to the text published by the GCBA (cited in testing-and-commissioning.md). **Not verified in a primary source:** what changes technically in 7-770 ed. 2026 and in 7-704 ed. 2026; AEA has not published an accessible summary of changes.

### ELEC-NOR-5: The construction site installation is a real installation, not a "provisorio" (temporary setup)
- **Rule:** the electrical installation of the site compound and the construction site is designed as a permanent one, according to the AEA (section 7-704 ed. 2026, or annex 771-B.7 of the 771 where the 704 has not yet been adopted) and Decreto 911/96, with earthing of all exposed conductive parts and automatic disconnection devices.
- **Why:** the construction site is where most electrocutions happen: cables that get stepped on, moisture, portable tools, people who are not from the trade. Decreto 911/96 displaces 351/79 in construction and has its own chapter on electricity.
- **How:** items of Decreto 911/96 you have to comply with:
  - Art. 74: safety voltage up to 24 V to earth in dry and damp locations; in wet locations it is set by the Health and Safety officer, without exceeding the MBTS (SELV). LV up to 1000 V between phases; MV from 1 to 33 kV; HV above 33 kV.
  - Art. 75: minimum distance between the worker (or their non-insulated tools) and non-insulated live parts: 0.8 m from above 24 V up to 1 kV, reducible to 0.60 m with suitable insulating screens over the live parts and no earthed metal grilles in between; 0.8 m from above 1 kV up to 33 kV. That distance is for work near other live parts: in LV, the right thing is to make dead what you are going to touch (ELEC-NOR-6), not to aim for the minimum.
  - Art. 86: outdoor wiring overhead or underground; indoor wiring embedded or suspended at no less than 2.40 m; overhead street crossings at no less than 8 m, with protective mesh; earthing of all exposed conductive parts and automatic disconnection; insulating gloves mandatory for handling LV cables; bare conductors without sheath or mesh prohibited; equipment and tools with an automatic disconnection switch and earthed metal parts. Note: gloves are additional protection against accidental energization; **they do not authorize handling live cables**. The same article requires de-energizing and checking the line first: switch off, lock out and verify (ELEC-NOR-6). Glove class and inflation test in ELEC-SEG-10 of [site-safety.md](site-safety.md).
  - Art. 87: periodic inspection; any operation of a protective device (MCB (*térmica*), RCD (*disyuntor*)) without a known cause requires inspecting the installation before resetting.
  - Art. 208: power tools (and their cables and accessories) with mechanical protection and suitable dielectric properties, and with a device that cuts the supply when the operator stops actuating them ("hombre muerto", dead-man cutoff; not to be confused with the RCD or the MCB); the person in charge of the task checks them before use.

  **Which AEA section applies on construction sites.** Until 7-704 ed. 2026, the construction site requirements were in annex 771-B.7 of the 771 ed. 2006, which is the one cited by the SRT guide for Res. 900/2015 and the one used in [site-safety.md](site-safety.md). Since AEA has not published an effective date for the 704 (see "Current editions"), check whether your jurisdiction or the Health and Safety service already requires it. If not, apply 771-B.7 and, where the 704 is stricter and both can be met, also the 704.
- **Verify:** the construction site panel has an RCD, MCBs (*termomagnéticas*) per circuit and a PE terminal connected to a measured earth rod (*jabalina*); site cables are not on the walkway floor or spliced with tape. Details in [site-safety.md](site-safety.md).
- **Don't:** hang the construction site panel on a nail with loose cables, power tools from homemade extension cords, or "puentear" (bypass) an RCD that trips.
- **Source:** Decreto 911/96 (BO 1996-08-14), arts. 74, 75 (table of distances and its note on insulating screens, in the row for above 24 V up to 1 kV), 86, 87 and 208 (text at argentina.gob.ar/normativa, re-read on 2026-11-15); art. 2 of Dec. 911/96, which excludes construction from Dec. 351/79 (Infoleg note on the text of Dec. 351/79 at argentina.gob.ar); AEA catalog (90364-7-704 ed. 2026); SRT practical guide for Res. 900/2015 (application of annex 771-B.7 to construction sites).

### ELEC-NOR-6: Work is done dead, under lockout/tagout (*consignación*); live work requires a separate authorization
- **Rule:** every intervention is done dead and with the installation locked out and tagged. Live work may only be done by personnel specially authorized by the company, with procedures from Res. SRT 3068/2014 (up to 1 kV, AEA 95705 regulation) or Res. SRT 11/2022 (above 1 kV, AEA 95702 regulation). This guide never instructs live work. Measuring live (RCD trip test, voltage at terminals) is not "live work", but it also has rules: see ELEC-NOR-10 and [testing-and-commissioning.md](testing-and-commissioning.md).
- **Why:** most electrical accidents in construction and maintenance come down to "era un minuto" (it was only a minute) or "creí que estaba cortado" (I thought it was switched off). The law defines the exact sequence and the responsibility of a single person, the Responsable del Trabajo (person in charge of the work).
- **How:** lockout/tagout according to Dec. 351/79 Anexo VI (and Dec. 911/96 art. 79 on construction sites):
  1. Isolate with a visible break from every voltage source (watch out for generators, UPS, solar panels and inverters, and backfeeds from another panel).
  2. Lock the switching device in the open position and place the "Prohibido Maniobrar" (do not operate) sign with the name of the person in charge.
  3. Verify absence of voltage with a suitable tester, tested before and after on a known source.
  4. Earth and short-circuit all points through which voltage could arrive. On construction sites Dec. 911/96 art. 79 a) and b) requires this in LV as well (the person in charge repeats it and checks it at the workplace); outside construction sites, Dec. 351/79 Anexo VI requires the same in its dead-work procedure. It is not an optional step.
  5. Mark and fence off the work area.
  Every installation is considered live until proven otherwise (Dec. 351/79 Anexo VI; Dec. 911/96 art. 78 b). When restoring, the person in charge personally checks that the earths and short-circuits, the tools, the locks and the personnel have been removed; on construction sites, also that the insulation resistance test has been done (Dec. 911/96 art. 79 c).
- **Verify:** there is a padlock or lock and a sign at the isolation point; the tester was tested; the person who restores is the same one who locked out.
- **Don't:** trust that "la térmica está baja" (the MCB is off) without locking out or measuring; use a non-contact voltage tester (*buscapolo*) as the only verification; use metal ladders or metal tape measures near live parts (Dec. 351/79 Anexo VI; Dec. 911/96 art. 78 c).
- **Source:** Decreto 351/79, Anexo VI, definitions of "bloqueo" (locking) and "consignación" (lockout/tagout), safety distances and LV dead-work procedure (text verified in a UNLP copy of the decree); Decreto 911/96 arts. 76 to 82, especially art. 79 a) III (lockout/tagout with earthing and short-circuiting of all access points), b) and c) (text at argentina.gob.ar/normativa, re-read on 2026-11-15); Res. SRT 3068/2014 (BO 2014-11-20), art. 1 (adopts the AEA 95705 regulation ed. 01, June 2013) and art. 4 (in force after 90 days); Res. SRT 11/2022 (RESOL-2022-11-APN-SRT#MT, signed on 2022-02-25, BO 2022-03-03): art. 1 approves the AEA "Reglamento para la Ejecución de Trabajos con Tensión en Instalaciones Eléctricas Mayores a 1 kV" (regulation for live work on electrical installations above 1 kV), Comisión 21, ed. 2020 (AEA 95702; the AEA catalog now lists a 2021 ed.), art. 3 repeals Res. SRT 592/2004 and art. 4 sets entry into force at 90 calendar days after publication (that is, from 2022-06-01). Step-by-step procedure in [site-safety.md](site-safety.md).

### ELEC-NOR-7: Where there are workers, earthing and continuity are measured and recorded in a protocol every year
- **Rule:** in every workplace (including construction sites and buildings with a caretaker), the earthing resistance measurement and the continuity check of exposed conductive parts are done with the Res. SRT 900/2015 protocol, which is valid for 12 months.
- **Why:** it is an employer obligation enforced by the ART and the SRT; in addition, the TT system used by every installation supplied in LV from the public grid depends on the RCD and the earth to protect against indirect contact.
- **How:**
  - Art. 1: the protocol is mandatory for whoever performs those measurements.
  - Art. 2: the measured values are valid for 12 months.
  - Art. 3: if the AEA values (earthing resistance or continuity) are not met, an action plan is drawn up to bring the installation into compliance.
  - Art. 4: the operation of automatic disconnection devices must be checked periodically (the SRT guide advises testing RCDs every month with the test button).
  - The protocol asks for, among other data, the earthing arrangement (TT, TN-S, TN-C, TN-C-S, IT) and the earthing value in ohm. In LV from the public grid the earthing arrangement (ECT) is TT, with no alternative (SRT guide, p. 4).
- **Verify:** there is a signed protocol less than 12 months old, with the instrument identified and an action plan if something failed. How to measure: [testing-and-commissioning.md](testing-and-commissioning.md) and [earthing.md](earthing.md).
- **Don't:** "measure" with a multimeter between phase and earth rod and record it as the earthing resistance.
- **Source:** Res. SRT 900/2015 and the "Guía práctica de interpretación de la Res. SRT 900/2015" (practical interpretation guide, SRT, at argentina.gob.ar), which supports the content of the items above. **Not verified in a primary source:** the date of publication in the Boletín Oficial (the rest of this guide uses 2015-04-28; other sources give 2015-04-23; Infoleg and argentina.gob.ar/normativa did not respond on 2026-11-15) and the exact correspondence between article number and content (arts. 1 to 4 as listed above, taken from the SRT guide); whether the protocol requires the signature of a licensed professional in all cases (in practice it is signed by a professional with the relevant scope).

### ELEC-NOR-8: The person who signs must have the scope (incumbencia) from their degree and a current license (*matrícula*) in that jurisdiction
- **Rule:** whoever signs a design, a DCI or a certificate must have scope in electrical installations granted by their degree (recognized by the education authority) and a current license with the professional council (*colegio* or *consejo profesional*) of the jurisdiction where the job is. The extent (power, voltage, type of premises) depends on the category and is set by each jurisdiction.
- **Why:** a DCI signed by someone without the scope is invalid and the utility may reject it; if there is an incident, signing without scope aggravates the liability of the signer and of the owner who hired them.
- **How:** a common scheme (Córdoba, city of Santa Fe) has three levels. The exact limits change by jurisdiction:

  | Level | Who | Typical scope | Backing |
  |---|---|---|---|
  | Categoría I | University professional with electrical scope (electrical engineer, electromechanical engineer...), licensed | According to the degree | **Not verified in a primary source** (scope in Córdoba Dec. 1022/2015 not confirmed) |
  | Categoría II | Technician with a qualifying degree with electrical scope, licensed | According to the degree | **Not verified in a primary source** |
  | Categoría III | Qualified person (idóneo) / trained and registered electrical installer | LV, up to 10 kW, single-family house and small shops, with exclusions | Córdoba, Dec. 1022/2015 art. 4, according to the ERSeP document "Competencia Cat. III" |

  To know whether an installation falls within a power cap, compare the project's maximum simultaneous power demand (DPMS), calculated as in [grades-and-circuits.md](grades-and-circuits.md), or the power to be contracted. The rating of the main protective device is not the power: it only gives an approximate upper bound (S ≤ U × In) and is chosen **afterwards**, based on the DPMS and the cross-section of the line. Downsizing the MCB to "fit" a category does not change the installation.

  Worked example (220 V single-phase; the DPMS comes out in VA):
  - Apartment with DPMS = 5500 VA. With cos φ ≈ 0.9: P ≈ 5500 VA × 0.9 = 4950 W. It fits within the 10 kW cap of Córdoba Cat. III and the T1R tariff (up to 10 kW).
  - Apartment with DPMS = 12 000 VA: P ≈ 12 000 VA × 0.9 = 10 800 W. It no longer fits Cat. III or T1R: the tariff and supply type indicated by the utility apply (usually three-phase).
  - Reference bound: 10 000 W / 220 V ≈ 45.5 A (with cos φ = 1).
  - Since we did not confirm whether the Cat. III cap refers to installed, demanded or contracted power, nor whether it is in kW or kVA, compare in VA without applying cos φ: that is the most conservative (5500 VA and 12 000 VA stay on the same side of the cap in both cases).

  The agent uses the `gateway electricidad` calculator (demand/grade) so as not to calculate this from memory.
- **Verify:** ask the signer for their current license card or certificate and check it in the council's register (COPIME in CABA; councils of technicians, of engineers or the ERSeP register in Córdoba, as the case may be). The Edenor and Edesur area covers CABA and districts of the Greater Buenos Aires conurbation: if the job is in the Province of Buenos Aires, the council is the provincial one (for technicians, the Colegio de Técnicos de la Provincia de Buenos Aires; for engineers, the Colegio de Ingenieros de la Provincia), not COPIME. **Not verified in a primary source:** the scopes each Buenos Aires province council recognizes for signing a DCI and which council licenses technicians in CABA; confirm it with the council before signing.
- **Don't:** accept a "matrícula de la AEA" (AEA license) or a "certificado de curso" (course certificate) as if they were a license: AEA does not license, and a non-recognized course does not grant scope by itself (see ELEC-NOR-12).
- **Source:** ENRE connection regulation (Res. 225/2011, 2022 ed. text), section II item 2 and section III item 2: signature by "profesionales, técnicos o instaladores electricistas con incumbencia específica homologada por la autoridad educativa competente, registrado en el Colegio Técnico o Profesional de la jurisdicción" (professionals, technicians or electrical installers with specific scope recognized by the competent education authority, registered with the Technical or Professional Council of the jurisdiction); Córdoba, Decreto 1022/2015 art. 4 (Cat. III, LV, up to 10 kW), according to the ERSeP document "Competencia de instaladores electricistas habilitados Categoría III". **Not verified in a primary source:** the scopes of Cat. I and II in Dec. 1022/2015; which quantity (installed, demanded or contracted power; kW or kVA) defines the 10 kW cap of Cat. III; the table attributed to ENRE that circulates on commercial websites (0-10 kW qualified person, 11-50 kW technician, more than 50 kW professional) was not found in any resolution; the caps of each council outside Córdoba must be confirmed with the council of the jurisdiction.
### ELEC-NOR-9: In Córdoba, no Certificado de Instalación Eléctrica Apta (certificate of a compliant electrical installation) means no supply
- **Rule:** in the province of Córdoba, every supply request covered by Ley 10.281 needs a Certificado de Instalación Eléctrica Apta issued by an Instalador Electricista Habilitado (authorized electrical installer) registered with ERSeP, with a category suited to the type, voltage and power of the installation.
- **Why:** the law makes it a mandatory condition: the utility (distribution company, *distribuidora*: EPEC or a cooperative) does not connect without the certificate, and whoever signs it becomes responsible for compliance with the law.
- **How:**
  - Enforcement authority: ERSeP (art. 3 of Ley 10.281). There is a register of authorized installers, an ERSeP technical regulation for installation and verification, a certificate administration procedure and a sanctions regime (RG ERSeP 26/2015, 05/2016, 49/2016, 08/2017, 46/2017 and amendments; sanctions regime amended by RG 42/2025).
  - Categoría III (qualified persons, idóneos): LV, up to 10 kW, single-family house and small shops or industries from a list. **They are prohibited from**, among others: common areas and common services of condominium buildings (*propiedad horizontal*, PH), construction supply (*luz de obra*) for apartment buildings or PH buildings (and for jobs above 10 kW), public assembly venues, premises that are damp or wet by their use (commercial laundries, cold rooms and the like) or with fire or explosion risk, pools, medical offices, schools and street lighting. Also excluded are premises whose use involves BA2/BA3 persons (kindergartens, nursing homes, facilities for people with disabilities) or classifications BD2 to BD4 or BE2 to BE4. The bathroom and kitchen of a dwelling, or children living in the house, do not place it within that exclusion: otherwise no Cat. III could certify a dwelling. **Not verified in a primary source:** the exact wording of this exclusion in the ERSeP document; whether an apartment in a PH building (a unit, not a "vivienda unifamiliar", single-family house) falls under Cat. III. If it is not clear, have a Cat. I or II sign, or consult ERSeP in writing.
  - Validity of the Cat. III authorization: RG ERSeP 96/2025 extended until 2026-04-30 the authorizations that had expired or were about to expire while a new mandatory training regime is defined. **As of 2026-11-15 we could not confirm what applies after that date:** check the ERSeP register.
- **Verify:** the installer appears in the ERSeP register with a current authorization and the category covers the use; the certificate was generated by the ERSeP system and includes the descriptive report, the plan view and the bill of materials.
- **Don't:** have a Cat. III sign the construction supply or the common services of an apartment building: it is expressly prohibited.
- **Source:** Córdoba Ley 10.281 (2015), arts. 3 and 5, and Decreto 1022/2015 art. 4, according to RG ERSeP 96/2025 (2025-08-19) and the ERSeP document "Competencia de instaladores electricistas habilitados Categoría III: instalaciones permitidas y prohibidas" (competence of Category III authorized electrical installers: permitted and prohibited installations) (ersep.cba.gov.ar). **Not verified in a primary source:** the full text of art. 2 of the law (which cases besides a new supply, for example reconnections or power increases, require a certificate).

### ELEC-NOR-10: Edenor/Edesur area (ENRE): the DCI is mandatory to connect a new supply
- **Rule:** in the Edenor and Edesur concession area (regulated by ENRE, now under ENReGE), a new single-phase T1R supply (dwelling, up to 10 kW) requires filing, before connection, a Declaración de Conformidad de Instalaciones Eléctricas (DCI, installation conformity declaration) or an equivalent municipal (or CABA) document. For three-phase T1R, T1G, T2 and T3 LV, the municipal approval or final inspection of works is required or, if it has not been issued yet, the start of the municipal procedure plus a DCI.
- **Why:** ENRE sets minimum public safety requirements for any installation connected to the grid. The DCI is the written record that a qualified professional inspected them on site.
- **How:** minimum requirements (section II item 3, single-phase T1R) that the DCI certifies:
  1. Main panel (distribution board, *tablero principal*) as close as possible to the meter.
  2. Insulating main panel, with double insulation.
  3. Minimum IP degree of protection according to IRAM 2444: IP 41 indoors, IP 54 outdoors. The ENRE PDF ed. 2022 says "IP 549": in the old three-digit notation (original IEC 529, NF C 20-010, IRAM 2444 of that time) the third digit was protection against mechanical impact, and 9 equals about 20 J, today IK10 (IEC 62262). In practice, ask for IP54 and an impact-resistant enclosure (IK10 or whatever the utility accepts) and confirm it with the utility; also check whether the indoor value appears as "IP 41x".
  4. No access to live parts.
  5. TT system with protective earthing according to AEA and IRAM 2281-2 and 2281-3 (now co-published as AEA 95501-2 and 95501-3).
  6. All exposed conductive parts connected to the protective earth.
  7. Two-pole MCB (*termomagnética*) per circuit in the main panel.
  8. RCD (*interruptor diferencial*) ≤ 30 mA in the main panel, protected against overload and short circuit (text replaced by Res. ENRE 269/2012).
  9. Using fuses to protect circuits in the main panel is prohibited.
  10. Materials certified to IRAM or IEC (the text still cites the "Marca S" (S mark) of Res. SICyM 92/98; see ELEC-NOR-14 for the current regime).

  The DCI form (Res. ENRE 269/2012) has five YES/NO items: main panel; RCD and MCBs; earthing system; certified materials; technical parameters of item 3. A single "NO" makes the installation NO CONFORME (non-compliant) and it is not approved. If there is a main panel and a sub-panel (*tablero seccional*), the MCB may go in the main panel and the RCD plus the two-pole MCBs per circuit in the sub-panel (note 2 of the form).

  When it is required (according to the Edesur guide): new meter, and a tariff change or power increase that involves changing the protective devices of the main panel or the service connection (*acometida*). Other procedures that may require a DCI or certificate (reinstating a supply that was cancelled, change of account holder after a prolonged disconnection, reconnection after a fire or incident) depend on each utility: **not verified in a primary source**, ask before quoting.
- **Verify:** before signing, go through the ten items and measure, in this order (details in [testing-and-commissioning.md](testing-and-commissioning.md)):
  1. **Dead, with the installation locked out and tagged (ELEC-NOR-6):** visual inspection of the panel with the inner cover (dead front, *contratapa*) removed, tightening of terminals, PE continuity to every socket outlet, insulation resistance (the megohmmeter applies 500 V DC: warn people and disconnect equipment) and earthing resistance (with the measuring link open, which leaves the exposed conductive parts without earth: that is why it is done with everything switched off and the link is closed again before energizing).
  2. **Live, with the inner cover or terminal cover fitted:** RCD trip test (with an IEC 61557-6 instrument and with the test button) and voltage at the output terminals of the main switch. These are measurements, not live work: they are done only by a trained person, with an instrument rated CAT III 600 V or CAT IV 300 V as a minimum (CAT IV at the meter pillar (*pilar*) and the main panel incomer) and probes with guards, with insulating gloves and safety glasses, without touching live parts ([site-safety.md](site-safety.md), ELEC-SEG-13).

  Also check the cases the utility itself lists as grounds for rejection: socket outlets that accept round-pin plugs, PE that does not reach all socket outlets, earth cable not run in conduit, sub-panel without an RCD, panel front that cannot be removed because of the masonry, unfinished work.
- **Don't:** sign a DCI "para la totalidad de la vivienda" (for the whole dwelling) if you only checked the panel; leave "universal" or round-pin socket outlets.
- **Source:** Res. ENRE 225/2011 (BO 2011-06-22), art. 1 and Anexo "Reglamento para la conexión de nuevos suministros" (rules for connecting new supplies; 2022 ed. text at argentina.gob.ar), sections II and III; Res. ENRE 269/2012 (DCI model and replacement of item 3.8); single-phase T1R DCI form (argentina.gob.ar, Feb 2018); Edesur, "Consideraciones sobre el certificado DCI", v1, January 2025; argentina.gob.ar/enre (as of 2026-11-15 it names only Edenor and Edesur as utilities in its area). **Not verified in a primary source:** the reading of "IP 549" as old notation with a mechanical third digit (technical reasoning on NF C 20-010 / IEC 529:1976: 1 = 0.225 J, 3 = 0.5 J, 5 = 2 J, 7 = 6 J, 9 = 20 J); in this review the PDF of the ed. 2022 regulation could not be re-read.

### ELEC-NOR-11: Construction meter pillar (*pilar de obra*) in the ENRE area: its own DCI, initial and annual
- **Rule:** to connect a construction meter pillar (T1G tariff, single-phase or three-phase) in the Edenor and Edesur area, the construction meter pillar DCI of Res. ENRE 380/2015 is filed, signed by a qualified professional. The form provides for initial and annual verification.
- **Why:** the construction supply is the installation that takes the most abuse and the one that stays outdoors the longest; ENRE sets for it the same core safety points as for a dwelling (panel, RCD, MCBs, earthing, certified materials).
- **How:** the construction meter pillar form (Anexo II of Res. 380/2015) repeats the five YES/NO items of the residential DCI, against Anexo I of that resolution, with the "Inicial / Anual" (initial / annual) box. If the job lasts more than a year, renew the verification.

  For a building (for example ground floor + 4), the site compound almost always needs three-phase: hoist or goods lift, concrete mixer, vibrators, saw, lighting and tools. Draw up the load estimate for the site compound and request the three-phase construction meter pillar with the resulting power; if it exceeds the T1G cap (10 kW, like the whole T1 tariff), the utility classifies it as T2 (more than 10 kW and less than 50 kW) or T3 (50 kW or more). Details of the site compound in [buildings.md](buildings.md) and of the construction site panel in [panels.md](panels.md).
- **Verify:** the construction meter pillar DCI is current (less than a year old) and the construction site panel is still as certified (on site it gets modified often).
- **Don't:** hook onto the neighbor's installation, or power the new construction of another unit or of a building from a residential T1R supply "mientras sale el pilar" (while the pillar comes through). A renovation within the same unit is different: there the existing supply is used, with its own construction site panel (30 mA ID (RCD), PIA (MCB) per circuit, PE to earth).
- **Source:** Res. ENRE 380/2015 (Expte. ENRE 36.207/2012), which approves the "Reglamento para la conexión de pilares de obra" (rules for connecting construction meter pillars) and the DCI form (summary on vLex); "Pilar de obra, DCI" form (argentina.gob.ar, Mar 2018); tariff limits T1 (up to 10 kW), T2 (more than 10 and less than 50 kW) and T3 (50 kW or more) according to the Edenor and Edesur tariff tables approved by ENRE. **Not verified in a primary source:** the full text of Anexo I of Res. 380/2015 (detailed technical requirements) and whether a construction meter pillar above 10 kW is processed with the same DCI of Res. 380/2015; the tariff limits are cited from memory of tariff tables, confirm them with the utility.

### ELEC-NOR-12: Before hiring, confirm that the signer can issue that document today
- **Rule:** being licensed is not enough: confirm that their registration allows them to issue that type of document (DCI, ERSeP certificate, municipal drawing) on the date of signing.
- **Why:** professional councils change scopes. Recent example: COPIME Res. 95/2026 (Consejo Profesional de Ingeniería Mecánica y Electricista, CABA; signed on 2026-04-28, BO 2026-05-11), arts. 4 to 7, excludes from issuing DCI-type commissions (encomiendas), from its entry into force, qualified persons (idóneos) with the CIMEBA certificate "Instalador Electricista – Nivel 3" (Electrical Installer, Level 3) (250 h) or from non-official institutes (courses of 250 h or more on AEA 90364-7-771) when they register for the first time or re-register, and those who hold the CIMEBA certificate, whose provisional registration expired and who passed the validation exam. It applies until that training is regularized and its recognition is ordered. A DCI signed by someone without that scope may be rejected.
- **How:**
  1. Ask for the current license card and check the number in the council's register.
  2. Ask explicitly: "¿tu matrícula te habilita a emitir DCI / certificado de instalación apta para esta potencia y destino?" (does your license authorize you to issue a DCI / certificate of compliant installation for this power and use?).
  3. Ask that the professional commission (encomienda profesional), if the council requires one, be registered or endorsed by the council.
  4. Recommended practice (not a verified general obligation): the signer should have current professional liability insurance; ask them for proof.
- **Verify:** the DCI shows the degree, license number and the body that granted it, and the commission is registered.
- **Don't:** accept a signature "porque el año pasado se la aceptaron a otro" (because last year it was accepted from someone else).
- **Source:** COPIME, Res. 95/2026 (2026-04-28, BO 2026-05-11, boletinoficial.gob.ar notice 341747), arts. 1, 2 and 4 to 7, and recitals (they cite Res. ENRE 269/2012). **Not verified in a primary source:** whether professional liability insurance is mandatory in each council.

### ELEC-NOR-13: Outside Córdoba and the ENRE area, the utility, the municipality and the professional council decide
- **Rule:** in the rest of the country, find out what the provincial utility or the cooperative requires, what the municipality requires and which professional council licenses, because the rule changes from place to place.
- **Why:** as of 2026-11-15 we did not find a provincial electrical safety law with an installer register in force in the Province of Buenos Aires or in Santa Fe (there have been and there are legislative bills). What applies there are municipal ordinances, utility regulations and the scopes of the professional councils.
- **How:** verified examples:
  - City of Santa Fe: Ordenanza 10236 (1997), "Reglamento de instalaciones eléctricas en inmuebles" (regulation of electrical installations in buildings), defines three levels of installers according to their degree; level 3 installers (qualified persons, idóneos) who have no professional council register with the municipality. A note from the City Council indicates that qualified persons must be licensed with the respective council and up to 20 kVA (secondary data).
  - EPE Santa Fe, distributed generation: requires a "Certificado de habilitación profesional" (professional authorization certificate) from the council, with scope in LV 220/380 V and a license in Santa Fe.
  - La Plata and the Edelap area (province of Buenos Aires): Edelap's official website shows OCEBA (Organismo de Control de Energía Eléctrica de la Provincia de Buenos Aires) as its oversight body, and the ENRE website names only Edenor and Edesur. Therefore the ENRE DCI and connection regulations (ELEC-NOR-10 and 11) are not the framework to apply there: follow Edelap's connection requirements (for example, its T1 service connection regulation, cited in [grades-and-circuits.md](grades-and-circuits.md)) and whatever OCEBA provides. The same goes for EDEA, EDES, EDEN and the Buenos Aires province cooperatives.
  - Mendoza: the Reglamento de Suministro (supply regulation) approved by EPRE makes the user responsible for everything from the municipal property line inward up to the main panel, according to standards approved by EPRE. The City of Mendoza processes the "Instalación eléctrica nueva" (new electrical installation) procedure with qualified professionals.
- **Verify:** you have in writing (official website or letter) the utility's list of requirements for that procedure and the municipality's confirmation.
- **Don't:** carry over the Córdoba or AMBA procedure to another province without confirming it.
- **Source:** City of Santa Fe Ordenanza 10236 (santafeciudad.gov.ar); EPE Santa Fe, "Manual para el tratamiento de solicitudes" (prosumers, rev. 7); Reglamento de Suministro EPRE Mendoza (epremendoza.gob.ar); City of Mendoza, "Instalación eléctrica nueva" procedure; edelap.com.ar (footer with logo and link to OCEBA, consulted 2026-11-15); argentina.gob.ar/enre (consulted 2026-11-15). **Not verified in a primary source:** the text of Decreto 1853/2011, which according to secondary sources (Marval O'Farrell Mairal, 2011-11-30; La Gaceta, 2011-11-17) ratified the Acta Acuerdo of 2011-03-18 and transferred the Edelap concession and jurisdiction to the Province of Buenos Aires in November 2011 (same as reviewing-a-panel.md, ELEC-REV-13), and whether Edelap currently requires a DCI or equivalent certificate for a new supply; the current legislative status of the electrical safety bills in Buenos Aires and Santa Fe; requirements of EDEA, EDES, EDEN and other provincial utilities.
### ELEC-NOR-14: Only materials with current certification and conformity marking
- **Rule:** install only electrical materials that comply with the current technical regulation and carry the conformity marking ("AR" mark with a double check mark and a QR code that links to the Declaración Jurada de Conformidad (sworn declaration of conformity) and to the certificate). A covered product that has neither the old mark nor the new one cannot be sold.
- **Why:** the DCI (installation conformity declaration) and the ERSeP certificate make you declare that the materials are certified. Counterfeit MCBs (*térmicas*), RCDs (*diferenciales*) and cables are a known cause of fires and of RCDs that don't trip.
- **How:** regime in force as of 2026-11-15:
  - **Materials for electrical installations** (socket outlets, plugs, switches, MCBs (*termomagnéticas*), RCDs, SPDs (*DPS*), isolators, cables, etc.): Res. SIyC 236/2024, with the Anexo II set by Res. SIyC 26/2025 (BO 2025-02-25; IF-2025-17295098-APN-DNRT#MEC, which replaced the original 2024 Anexo II: see [iram-standards.md](iram-standards.md) ELEC-IRA-2 for the current item numbering), and Disposición DNRT 2/2025 (BO 2025-04-15), scope from 50 to 1000 V AC and from 75 to 1500 V DC; materials above 63 A are excluded, except cables.
  - MCBs, RCDs (also those with integrated short-circuit protection), switch-disconnectors (*interruptores manuales*) and LV switches, SPDs, isolators and cables (fixed indoor cables, cords, and power or control cables) can only be certified under schemes 1b or 5 (Disp. 2/2025, point 5.2.3). The certificate is valid for 2 years and is maintained with surveillance records.
  - Certificates issued under the old Res. 169/2018 were valid for up to 12 months from the entry into force of Disp. 2/2025, that is, until mid-April 2026. They have expired.
  - **Fixed socket outlets** up to 250 V and 20 A: with earth contact, IRAM-NM 60884-1 or IEC 60884-1, and **outlets that accept plugs of different geometries at the same time ("universales", universal) are banned**. **Plugs**: with earth per IRAM 2073; without earth (up to 10 A) per IRAM 2063. **Power strips and extension cords** (*zapatillas y prolongadores*): earthed socket outlets, a legend of 10 A maximum simultaneous load, and an automatic limiter at 10 A on multi-outlet units.
  - **Marking**: since 2025-10-01 enforcement requires the new marking. The old safety mark may coexist only on stock manufactured or imported before that date (proven with an invoice). A product manufactured later with the old mark is in breach.
  - Household appliances, lighting and power supplies: Res. 16/2025, which repealed Res. 169/2018; machines and tools: Res. 17/2025.
- **Verify:** on the box or the product: AR marking with double check mark and QR; scan the QR and confirm that the certificate matches that model and is current; product standard printed (for example, IEC 60898-1 for MCBs or IEC 61008-1 / 61009-1 for RCDs; IRAM 2169 and 2301 are withdrawn, see [iram-standards.md](iram-standards.md) ELEC-IRA-7) and ratings (In, Icn, IΔn, curve). In dwellings, the PIAs must be IEC 60898-1 (there is no equivalent current IRAM standard): a breaker certified only to IEC 60947-2 is for industrial panels operated by instructed personnel (BA4/BA5), not for the panel operated by ordinary users (BA1/BA2); the difference between Icn and Icu is in [protection.md](protection.md). For socket outlets, check that they are not "universales" (universal).
- **Don't:** buy MCBs or cable with no brand and no marking "because they're the same"; accept materials the client brings without checking them (if you install them, you sign for them).
- **Source:** Res. SIyC 236/2024 and Res. SIyC 26/2025 (BO 2025-02-25), art. 1 (new Anexo II IF-2025-17295098-APN-DNRT#MEC) and art. 4 (marking required from 2025-10-01), per [iram-standards.md](iram-standards.md) ELEC-IRA-2; Disposición DNRT 2/2025 and its Anexo IF-2025-38164600-APN-DNRT#MEC (points 1, 2, 4.1, 5.2.2, 5.2.3 and 5.3; art. 3 on the transition from Res. 169/2018); Providencia DNRT PV-2025-120654504 (2025-10-30), "Marcado de conformidad - Res. SIyC 237/24" (conformity marking); argentina.gob.ar, service "Marcado de conformidad"; TÜV Rheinland summary of Res. 16/2025, 17/2025 and 236/2024. The product standards IEC 60898 / 61008 / 61009 cited as examples are general technical references; details in [protection.md](protection.md). IRAM 2169 and 2301 are listed as withdrawn in the IRAM catalog (ELEC-IRA-7). **Not verified in a primary source:** the AEA clause that reserves IEC 60947-2 breakers for BA4/BA5 personnel (common practice, not reread in the standard).

### ELEC-NOR-15: Know where the utility (*distribuidora*) ends and where you start
- **Rule:** the utility's (distribution company's) installations (service connection (*acometida*) and meter) reach up to the first isolating device after the meter (the user's panel). From the terminals of that first isolating device inward, everything is the user's responsibility (and that of the professional who designed, built or certified it). The cabinet or meter pillar (*pilar*) that houses the meter is supplied and maintained by the user according to the utility's model.
- **Why:** it defines who pays, who repairs and who is liable if there is an accident. Tampering with the meter, the seals or the service connection is illegal and dangerous: upstream of the first disconnection point there is no user protection to save you.
- **How:** user obligations under the ENRE Reglamento de Suministro (supply regulations):
  - Install and maintain, at the meter output and in the main panel, protection suited to the supply capacity according to the regulator's rules, the AEA or the local standard (item c).
  - Keep meter cabinets clean, dry, signposted, lit and accessible; keep the installations downstream of the first isolating device in perfect condition (item d).
  - Don't handle, repair or modify the utility's installations between the connection and the first isolating device; report any broken seals (item e).
  - Limit use to the contracted power and request authorization before increasing it (item g). If the increase requires changing the protection in the main panel or at the service connection, a new DCI is required (ELEC-NOR-10).
  - The utility may inspect up to the input terminals of the first isolating device after the meter.
- **Verify:** the first isolating device (MCB or main switch) is immediately after the meter, accessible, and rated for the contracted power.
- **Don't:** open the meter box, bypass or "upsize" the main protection beyond what is contracted; work on the meter pillar with the service connection connected. **Danger:** the input terminals of the first isolating device are always live unless the utility cuts the supply; to work there, ask the utility to cut it.
- **Source:** Reglamento de Suministro de Energía Eléctrica ENRE (electricity supply regulations; text updated per Anexo IV of Res. ENRE 524/2017 and Anexo V of Res. ENRE 525/2017), chapter on user obligations, items c), d), e), f), g), and section "Inspección y verificación del medidor" (meter inspection and verification). In other provinces the supply regulations of their own regulator apply (for example, those of the EPRE in Mendoza).

### ELEC-NOR-16: Each party answers for its own part, and a signature is not lent
- **Rule:** put in writing who designs, who builds, who supervises and who certifies, and make sure each one signs only what they did or verified personally.
- **Why:** the professional who signs the DCI "es el responsable de que la misma refleje las verdaderas características de la instalación" ("is responsible for ensuring that it reflects the true characteristics of the installation") (Edesur), and the utility can report them to their professional council. In Córdoba, by signing the certificate the installer "se constituye en responsable" ("becomes responsible") for compliance with the law.
- **How:** usual division of responsibilities:

  | Party | Answers for |
  |---|---|
  | Owner / user | Hiring someone qualified; maintaining the installation downstream of the first isolating device; not increasing the power without authorization; as an employer, complying with Ley 19.587 (annual SRT 900/2015 protocol) |
  | Designer | That the design complies with the AEA (correct section, current edition) and the local standard |
  | Installer / contractor | Building according to the design and the AEA with certified materials; working dead (Dec. 351/79 or 911/96) |
  | Site supervisor (*director de obra*) | Checking that the work matches the design; coordinating site safety with the Health and Safety (*Higiene y Seguridad*) officer |
  | Signer of the DCI or certificate | Having inspected on site and that what is declared is true on the date of signing |
  | Utility | Service connection, meter and network up to the first isolating device; requiring the documentation before connecting |
  | Municipality / authority | Permits, inspections, registers and sanctions within its jurisdiction |

  Keep in the job file the design with the AEA edition, the test schedules (insulation, PE continuity, earthing (PAT), RCD tripping), the photos of the panel without the inner cover (dead front, *contratapa*) taken dead before closing, and the copy of the DCI or certificate. What is handed over to the user or the owners' association (*consorcio*) is in ELEC-NOR-20.
- **Verify:** the file exists and each document has a signature, license (*matrícula*) number and date.
- **Don't:** sign a DCI for an installation you have not seen, or "lend your license" to whoever did the work.
- **Source:** Edesur, "Consideraciones sobre el certificado DCI" (considerations on the DCI certificate) (January 2025), point 1 and point 3 (report to the licensing body); Ley 10.281 of Córdoba, art. 5, per ERSeP documentation; ENRE Reglamento de Suministro, user obligations. **Not verified in a primary source:** the civil-law framework (Código Civil y Comercial de la Nación (national Civil and Commercial Code), arts. 1273 to 1277 on ruin of the work (*ruina de obra*), which cover the builder, the designer and the site supervisor, and arts. 1757-1758 on strict liability for dangerous things and activities). In a dispute, consult a lawyer.

### ELEC-NOR-17: Schedule periodic inspections even if nobody asks for them
- **Rule:** recommend to the owner or owners' association (*consorcio*) a periodic inspection by a qualified professional: dwellings every 5 years; offices, shops and common areas of condominium buildings (*propiedad horizontal*, PH) every 3 years; places of public assembly every 2 years; premises with fire or explosion risk every year. Where there are workers, also the SRT 900/2015 protocol every 12 months.
- **Why:** installations degrade (loose connections, RCDs that stick, DIY extensions). The ENRE recommends it and AEA 90364-6 regulates periodic verification.
- **How:** write the date of the next inspection in the handover report; in buildings, coordinate with the building management (see [buildings.md](buildings.md)). The verification procedure is in [testing-and-commissioning.md](testing-and-commissioning.md) and the panel review in [reviewing-a-panel.md](reviewing-a-panel.md).
- **Verify:** the handover report has the date of the next inspection and the person in charge.
- **Don't:** confuse the monthly RCD test-button check (done by the user) with a professional inspection.
- **Source:** ENRE connection regulations (Res. 225/2011, 2022 edition text), section II point 5 (every 5 years, dwellings) and section III point 5 (5, 3, 2 and 1 years depending on use); AEA 90364-6 ed. 2025 (initial and periodic verification). **Not verified in a primary source:** the exact intervals in AEA 90364-6 ed. 2025 (an unofficial copy mentions 2 years for public assembly and 1 year for fire or explosion risk, which match the ENRE).

### ELEC-NOR-18: The ENRE became the Ente Nacional Regulador del Gas y la Electricidad; its resolutions remain in force
- **Rule:** keep applying the ENRE resolutions (225/2011, 269/2012, 380/2015, Reglamento de Suministro), but look up the current forms and requirements on the website of the utility and of the new regulator, because they may change.
- **Why:** Decreto 452/2025 (BO 2025-07-07) constituted the Ente Nacional Regulador del Gas y la Electricidad (national gas and electricity regulator, ENReGE), created by Ley 27.742, merging the ENRE and the ENARGAS. According to the official ENRE website, since May 2026 the ENReGE has been progressively taking over its functions; until the new structure is approved, the existing units and functions continue.
- **How:** in new documents cite "Res. ENRE n.º/año (hoy en el ámbito del ENReGE)" ("Res. ENRE no./year (now under the ENReGE)"). Before submitting a DCI, download the current form from the utility's website.
- **Verify:** the date the form was consulted is noted in the job file.
- **Don't:** treat the ENRE resolutions as repealed because of the change of regulator: we found no resolution that repeals them.
- **Source:** Decreto 452/2025 (Boletín Oficial, 2025-07-07); argentina.gob.ar/enre, "Organigrama, autoridades y personal" (organization chart, authorities and staff) (ENReGE since May 2026; Decreto 318/2026 on the board); argentina.gob.ar/enre, home page (accessed 2026-11-15: uses the acronym "ENReGE" and announces the ENReGE website on 2026-09-15). The press sometimes writes "ENRGE": it is the same body; this whole guide uses "ENReGE" (see also ELEC-DIA-13). **Not verified in a primary source:** the exact start date of its functions (secondary sources say 2026-05-14).

### ELEC-NOR-19: Electro-dependent users (*electrodependientes*): full DCI or documented dedicated circuit
- **Rule:** when a user registered as electro-dependent asks the utility for an alternative power source (FAE, *fuente alternativa de energía*), submit a DCI issued for the whole dwelling or, as an alternative, for a dedicated independent circuit with a single socket outlet for the FAE, with a dimensioned drawing.
- **Why:** Ley 27.351 (2017) recognizes people who depend on electricity for health reasons and the provision of an alternative source by the utility; in the ENRE area, Res. ENRE 544/2017 requires the DCI as an obligation of the electro-dependent user, and the FAE is not installed if the utility's verification finds deviations. In other areas (for example, Edelap), check the procedure of the utility and of the provincial regulator.
- **How:** according to the Edesur guide, only two options are valid:
  - Option 1: DCI for the entire dwelling, with the corresponding legend under "Observaciones" (Remarks).
  - Option 2: DCI for an independent circuit (Nota ENRE NO-2021-82208385-APN-ENRE#MEC, 2021-09-02), with its own sub-panel (TS, *tablero seccional*), PE, an IRAM 2071 socket outlet and a drawing with the dimensions of the socket outlet's location.
  The utility checks, among other things, that the voltage at the FAE socket outlet is greater than 95 % of the voltage measured at the output terminals of the main MCB. Example: if you measure 225 V at the output of the main breaker, you must measure more than 225 V × 0.95 = 213.75 V at the socket outlet. If you measure 210 V, the voltage drop is excessive and the FAE is not installed.

  How to measure so the test is valid: with the FAE circuit **loaded** (with the equipment that will be connected or a test load of similar current), and both readings at the same time (two instruments) or one right after the other, under the same network conditions. Without load, the drop in the cable is practically zero (ΔU = I × R, with I ≈ 0 A gives ΔU ≈ 0 V) and any circuit "passes" even if it is undersized. This is a live measurement: inner cover or terminal cover in place, instrument CAT III 300 V minimum, probes with guards, gloves and safety glasses, without touching live parts (ELEC-NOR-10, Verify). The design voltage drop is calculated with the `gateway electricidad` calculator.
- **Verify:** correct legend on the DCI, drawing attached if Option 2, documented voltage measurement under load (test current and both voltages).
- **Don't:** "adapt" an existing shared circuit and declare it independent.
- **Source:** Edesur, "Consideraciones sobre el certificado DCI" v1 (January 2025), points 1, 2 and 6, which cite Res. ENRE 544/2017 (Anexo I, point A, item 4) and Nota ENRE NO-2021-82208385-APN-ENRE#MEC. **Not verified in a primary source:** the text of Ley 27.351 and of Res. ENRE 544/2017 (argentina.gob.ar/normativa did not respond on 2026-11-15); they are cited through the Edesur guide.
### ELEC-NOR-20: When you finish, hand the documentation over to the user or the owners' association (*consorcio*)
- **Rule:** when you close a job or a certification, hand over in writing to the owner or the owners' association (*consorcio*): as-built drawings (*planos conforme a obra*), an updated single-line diagram (*unifilar*) (a copy stuck or stored inside the panel), a test schedule (*planilla de ensayos*: insulation, PE continuity, earthing (PAT), tripping of each RCD) with instrument and date, a copy of the DCI (installation conformity declaration) or the certificate, and user instructions (*instructivo*).
- **Why:** without a single-line diagram or schedule, the next person who opens the panel (distribution board, *tablero*) works blind, and the owners' association cannot prove to the ART (workers' compensation insurer), the insurer or a judge that the installation was handed over in good condition. The user has to know what to do (and what not to do) with what is handed over.
- **How:** the instructions say, at a minimum:
  1. Test each RCD (*disyuntor* / *diferencial*) once a month with the test button: it must trip; if it doesn't trip, call an electrician and don't use that circuit.
  2. What each MCB (*térmica*) feeds (labels on the panel that match the single-line diagram).
  3. Don't add circuits, don't replace MCBs with higher-rated ones, and don't bypass the RCD.
  4. Date of the next professional inspection (ELEC-NOR-17) and, if there are workers, of the next SRT 900/2015 protocol (ELEC-NOR-7).
- **Verify:** the user signs a receipt listing the documents; the single-line diagram inside the panel matches what is installed.
- **Don't:** hand over only the DCI; leave a panel without labels or a single-line diagram.
- **Source:** recommended professional practice; AEA 90364-6 ed. 2025 (initial verification and its documentation) and AEA 90364-7-771/7-770 (panel documentation and diagrams), clauses not reread; SRT practical guide to Res. 900/2015 (monthly RCD test-button check). **Not verified in a primary source:** the exact list of documents that the AEA requires to be handed over; details of the tests in [testing-and-commissioning.md](testing-and-commissioning.md) and of the single-line diagram and labels in [panels.md](panels.md).

### ELEC-NOR-21: On a site with workers, electricity is part of the site safety file
- **Rule:** on a construction site with employed workers (*en relación de dependencia*), the construction supply installation and the electrical work fall under the site's occupational safety framework: notice of works (*aviso de obra*) to the ART, site safety file (*legajo técnico*), safety program and Health and Safety service (*Higiene y Seguridad*, HyS), in addition to the utility's DCI or certificate.
- **Why:** the electrician does not work alone: the construction company (employer) answers to the ART and the SRT for site safety. The HyS officer sets, for example, the safety voltage in wet locations (Dec. 911/96 art. 74) and is the one who endorses personnel authorization for live work (Dec. 351/79 Anexo VI, outside construction sites).
- **How:**
  - Ley 19.587 and Decreto 911/96 (health and safety regulations for construction), with its chapter on electricity (arts. 74 to 87) and the site's Health and Safety service.
  - Res. SRT 231/96 (site safety file), 51/97 (notice of start of works and Programa de Seguridad (safety program)), 35/98 (safety coordination between contractors and subcontractors) and 319/99 (repetitive or short-duration works); Res. SRT 61/2023 cites them as in force.
  - Ask for the construction site panel, the meter pillar (*pilar*), the cable routing and the lockout/tagout (LOTO) procedure (ELEC-NOR-6) to be included in the Programa de Seguridad, and for the HyS officer to review them before energizing.
  - If you are an electrical subcontractor, give the main contractor your own program or adherence, the staff list with ART coverage, and the record of PPE delivery (Res. SRT 299/2011).
- **Verify:** on site there is a site safety file and a Programa de Seguridad that covers electrical risk, and an identified HyS officer.
- **Don't:** treat the construction supply (*luz de obra*) as "the electrician's business" outside the safety program; start working as a subcontractor without being included in the program.
- **Source:** Decreto 911/96, arts. 74 to 87 (reread on argentina.gob.ar/normativa on 2026-11-15); Res. SRT 231/96, 51/97, 35/98 and 319/99 per Res. SRT 61/2023 (cited in [site-safety.md](site-safety.md)); Res. SRT 299/2011. **Not verified in a primary source:** the text of each SRT resolution in this list and the articles of Dec. 911/96 that organize the HyS service; as far as we know, there is no formal "approval" of the construction site panel separate from the construction-site meter pillar DCI and the safety program.

### ELEC-NOR-22: Distributed generation: no export to the grid without the utility's authorization
- **Rule:** equipment that can export energy to the grid (panels with a grid-tied inverter) is connected only after the user-generator (*usuario-generador*) procedure under Ley 27.424 (or the provincial regime where the province did not adhere), carried out by a qualified installer, and with the bidirectional meter installed by the utility (distribution company, *distribuidora*).
- **Why:** a badly configured inverter can energize the grid during an outage and electrocute whoever is working on it; also, without the procedure the utility can cut the supply. It is an increasingly common procedure and has its own paperwork track, separate from the DCI.
- **How:** national framework: Ley 27.424, Decreto 986/2018 and Res. ex-SGE 314/2018 with its amendments (the annex of categories and power ratings was replaced by Res. SE 287/2025). The inverter power reaches, as a general rule, up to the contracted power. The installation is done by an authorized qualified installer, who uploads the documentation to the national platform; the utility installs the bidirectional meter. In provinces with their own regime (for example, EPE Santa Fe, ELEC-NOR-13), the professional council's approval and the utility's requirements are required. Step by step, protection and technique in [special-installations.md](special-installations.md) (ELEC-ESP-20 onward).
- **Verify:** the user has the approved power reservation and the bidirectional meter request form submitted before connecting; the installer is listed as qualified.
- **Don't:** connect the inverter to the grid "to test it" before authorization; sign as a qualified installer without being registered.
- **Source:** argentina.gob.ar, "Generación distribuida" (distributed generation) (accessed 2026-11-15: the installation "deberá ser realizada por un Instalador Calificado autorizado", "must be carried out by an authorized Qualified Installer"); Ley 27.424, Decreto 986/2018, Res. ex-SGE 314/2018 and Res. SE 287/2025 per [special-installations.md](special-installations.md). **Not verified in a primary source in this review:** the text of Ley 27.424 and its implementing regulations; which provinces had adhered as of 2026-11-15.

## Application to the example case: 4-story building, single-phase units

Case: condominium building (*propiedad horizontal*, PH) with ground floor plus 4 stories, apartments (*deptos*) each with a single-phase T1R
supply, plus common services (landings, pump, door entry system and, if any, elevator). Which papers and standards apply:

| Stage / area | Technical standard | Procedure / paper | Who signs |
|---|---|---|---|
| Feasibility and power request for the building | Utility requirements; AEA 95150 | Written request with the load forecast; the reply defines cabinets, meter location, prospective short-circuit current (Icc) and whether a transformer vault or substation is needed (see [buildings.md](buildings.md), ELEC-EDI-1) | Qualified designer |
| Site occupational safety | Ley 19.587; Dec. 911/96; Res. SRT 51/97, 35/98, 319/99 | Notice of works, site safety file, Programa de Seguridad covering electrical risk (ELEC-NOR-21) | Employer and Health and Safety officer |
| Construction supply | Dec. 911/96 arts. 74-87; AEA 7-704 or annex 771-B.7 (ELEC-NOR-5) | Three-phase construction-site meter pillar sized to the site compound's load forecast. ENRE area: construction-site meter pillar DCI (Res. 380/2015), initial and annual. Córdoba: ERSeP certificate (Cat. III **cannot**). Other areas (Edelap included): utility requirements | Qualified professional or technician (Cat. I or II in Córdoba) |
| Each apartment | AEA 7-771 + 7-701 (bathrooms) | ENRE area: single-phase T1R DCI per unit (Res. 225/2011 and 269/2012). Córdoba: certificate per unit | Qualified person whose scope covers the unit's power (ELEC-NOR-8). Córdoba: confirm with the ERSeP whether an apartment in a PH falls under Cat. III (the list says single-family house); if unclear, Cat. I or II |
| Common services | AEA 7-772 (+ 7-791 if there is an elevator) | If three-phase or T1G: municipal approval or start-of-works filing + DCI (section III). Córdoba: Cat. III **cannot** | Qualified professional or technician |
| Meters (bank or cabinets) | Utility specification; AEA 95150 | Supply request per unit, with that unit's DCI or certificate; the shared cabinet per the drawing approved by the utility | The signer of each per-unit DCI or certificate |
| Municipal final completion approval (*final de obra*) | Local building code (CABA: Ley 6100 amended by Ley 6438) | Electrical drawing or documentation in the final completion file, if the municipality requires it (ask at the start; **not verified** for CABA) | Qualified professional as the municipality defines |
| Handover | AEA 90364-6 (initial verification) | As-built drawings, single-line diagrams, test schedule, user instructions (ELEC-NOR-20) | Signer of each DCI / site supervisor |
| Use (with a building caretaker or workers) | Res. SRT 900/2015 | Earthing (PAT) and continuity protocol every 12 months | Professional with the relevant scope (*incumbencia*) |

The technical design of the building (sub-mains, risers (*montantes*), panels per floor) is in [buildings.md](buildings.md);
the panel in [panels.md](panels.md) and [reviewing-a-panel.md](reviewing-a-panel.md).

## What this guide does not replace

- The design, supervision and signature are done by a qualified professional, technician or installer according to the
  jurisdiction and their professional scope. The agent guides and cites standards: it does not sign or certify.
- The utility decides what it accepts for connection, and the municipality or the provincial authority decide approvals,
  inspections and registers. If they differ from this guide, what they say in writing prevails.
- The AEA and IRAM regulations must be bought in their current edition; this guide only summarizes them.
- Standards change: this guide reflects what was verified as of 2026-11-15. Before a procedure, check the date of
  the sources.
