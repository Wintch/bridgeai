---
title: Survey and drawings of an existing installation (even with no drawings)
scope: survey by eye a house, shop or office in Argentina and draw it with standardized symbols; tools used today (sketches, phone apps, CAD, diagrams, BIM) and exchange formats; IRAM 2010 / IEC 60617 symbols; map which MCB feeds each outlet point without risk; workflow with the agent and the `gateway electricidad plan` tool (survey.json, validate, draw, single-line, per-circuit sheets, DXF, status); phases of teamwork on the drawing (mapping, diagnosis under group lockout, sectioning, per-circuit lockout); as-built drawing at the end
when_to_use: an installation must be worked on and there are no drawings or they cannot be trusted; several people will work in parallel and each needs their own isolated sheet; the person sends a hand sketch or photos and asks "armame el plano" (make me the drawing); circuits must be identified in a badly labeled panel; a job is finished and the as-built must be delivered
related: [README.md, regulations-and-permits.md, grades-and-circuits.md, conductors-and-conduits.md, protection.md, earthing.md, panels.md, buildings.md, site-safety.md, testing-and-commissioning.md, troubleshooting-common-cases.md, reviewing-a-panel.md, teamwork-and-rehabilitation.md, iram-standards.md, current-ratings-and-devices.md]
as_of: 2026-11-15
sources: [AEA 90364-7-770 Ed. 2017 (770.1 scope; 770.2.1 design project; 770.6.6 a) and b), note 1 and table 770.6.I: what an outlet point is and maximum outlet points per circuit; 770.7.1 l) boxes in the slab and m) socket outlets on the lighting circuit; 770.7.2 location and heights of socket outlets, socket outlets in the panel; Anexo 770-A technical documentation, mandatory, with its note on the as-built; Anexo 770-D informative, normative and regulatory references, includes IRAM 4504), AEA 90364-7-771 Ed. 2006 (table 771.7.I, limits for offices, shops and dwellings outside the scope of the 770; per grades-and-circuits.md ELEC-CIR-5), AEA 90364-7-772 Ed. 2019 (772.4.4 as-built documentation; per the index), IRAM 2010 Sección IV "Símbolos gráficos electrotécnicos para instalaciones de alumbrado, calefacción y fuerza motriz" (electrotechnical graphic symbols for lighting, heating and motive power installations) (consulted in the reproduction in the UNCuyo course notes, Facultad de Ingeniería, "Dibujo instalaciones eléctricas básicas", Apéndice II), IRAM 2010-1/-3/-6 (titles, same course notes), UTN FRRo, Castro and Juzefiszyn, "Proyecto de instalaciones eléctricas v3" (2014, drawing conventions and colors), IEC 60617 (graphic symbols database), IEC 60417-5017 and -5019 (earth), buildingSMART IFC 4.3 (IfcOutlet, IfcSwitchingDevice, IfcProtectiveDevice, IfcElectricDistributionBoard deprecated in favor of IfcDistributionBoard; IFC4.3.x-development repository), Apple RoomPlan (developer.apple.com, consulted 2026-11-15), magicplan (App Store and help center "export formats", consulted 2026-11-15), QElectroTech (qelectrotech.org, v0.100, GPLv2+), LibreCAD (librecad.org, GPLv2), QCAD (qcad.org and qcad.ch, QCAD 27; Community Edition GPLv3 without DWG, DWG only in Professional), FreeCAD (freecad.org, 1.1), BricsCAD (bricscad.octave.com, formerly Bricsys; Lite, Pro, Ultimate and BIM and Mechanical toolsets, consulted 2026-11-15), draw.io (drawio.com, Apache 2.0; Electrical and Floorplan palettes in the jgraph/drawio repository), Res. SRT 900/2015 (sketch with numbered points), Res. SRT 3068/2014 (live work up to 1 kV, AEA 95705), Decreto 351/79 Anexo VI and Decreto 911/96 arts. 78-79 (dead work, lockout, re-energizing), teamwork-and-rehabilitation.md (ELEC-EQU-5, 7 to 9, 17 to 28: phases, group lockout, coordinated insulation testing, re-energizing)]
---
# Survey and drawings of an existing installation

How to go from "there are no drawings, nobody knows which MCB (*térmica*) is which" to a simple drawing, with symbols any
Argentine electrician understands, an isolated sheet per circuit for each technician and a record of progress. Each rule
has a stable ID (ELEC-PLA-n) so the agent can cite it ("see ELEC-PLA-11") and so `gateway electricidad plan
validate` can name it in its warnings.

**What it is and what it is not.** What comes out of here is a **survey sketch** (*croquis de relevamiento*): approximate
measurements, location of outlet points (*bocas*), circuits and protective devices as found. It serves to organize the work
and to avoid working on the wrong circuit. It is **not** a signed design project or an as-built drawing (ELEC-PLA-21,
ELEC-PLA-22). The AEA, IRAM and IEC standards are paid: here they are described and the clause is cited, they are not copied.

**Safety first.** Surveying is **looking, measuring distances and testing socket outlets (*tomas*) from the outside**. Nobody opens a
box, removes a switch cover plate or an inner cover (dead front, *contratapa*) while live "to see where the cable comes
from". What the map says ("this outlet point is on C3") is a hypothesis until the tester, on the spot, reads 0 V after
locking out (ELEC-PLA-16, [site-safety.md](site-safety.md) ELEC-SEG-3 to 5). In a house with MCBs tripping because of
leakage or short circuits, a tripped MCB **is not switched back on to map** (ELEC-SEG-22).

## Quick reference
| Situation | Rules |
|---|---|
| What do I draw with? App, CAD, paper? | ELEC-PLA-1 |
| In what format do I pass the drawing to someone else? | ELEC-PLA-2 |
| What does a submission require (utility, municipality, professional council)? | ELEC-PLA-3 |
| What symbols do I use? Which standard applies? | ELEC-PLA-4, symbol table |
| Numbering circuits, switch letters, conduit labels, colors | ELEC-PLA-5 |
| Before going in to survey | ELEC-PLA-6 |
| Sketch per room, measurements by eye | ELEC-PLA-7 |
| Numbering and photographing outlet points | ELEC-PLA-8 |
| What to record for each outlet point, panel (*tablero*) and protective device | ELEC-PLA-9 |
| Heights | ELEC-PLA-10 |
| Which MCB feeds each outlet point? | ELEC-PLA-11, ELEC-PLA-12, ELEC-PLA-13 |
| Circuits that cannot be energized (leakage, short circuit) | ELEC-PLA-11 (dead variant) |
| Labeling the panel | ELEC-PLA-14 |
| Shared neutrals, circuits from another panel, outlet points that never go off | ELEC-PLA-15 |
| "I'll open the box so I can see" | ELEC-PLA-16 |
| The person sends a sketch or photos to the agent | ELEC-PLA-17 |
| Before drawing or handing out sheets | ELEC-PLA-18 |
| Per-circuit or per-technician sheets | ELEC-PLA-19 |
| Tracking progress | ELEC-PLA-20 |
| Several technicians: what phase the job is in and what gets locked out | ELEC-PLA-24, ELEC-PLA-19 |
| A junction box with cables from several circuits | ELEC-PLA-25 |
| What is this drawing worth? | ELEC-PLA-21 |
| Finishing the job: as-built | ELEC-PLA-22, ELEC-PLA-23 |

## What is used today to survey and draw

Comparison as of 2026-11-15. No prices: "paid" means a commercial license (subscription or perpetual depending on the
product); check the terms on the manufacturer's site before buying.

| Tool | Type and license | Exports | Good for | Limits for this use |
|---|---|---|---|---|
| Dimensioned hand sketch (grid paper, drawing board) | Free | Photo, scan to PDF | Surveying on site, fast, no battery; the agent reads it from a photo | Not to scale unless you take care; gets erased or lost; must be transcribed |
| magicplan | iOS/Android app, free with paid time-based plans | PDF (report or floor plan only), SVG, JPG/PNG, DXF (**without dimensions**), IFC, OBJ, USDZ, CSV of areas | Room floor plan with the camera or LiDAR, photos and notes per room | Aimed at renovation/insurance; Argentine electrical symbols not confirmed; the DXF comes out without dimensions |
| Apps based on Apple RoomPlan (LiDAR) | Apple API; used by several third-party apps, each with its own license | USD/USDZ (3D) as a base; each app adds its own formats | Scan a room in seconds with an iPhone/iPad Pro with LiDAR: walls, openings, furniture | Requires a device with LiDAR; does not detect electrical outlet points; they must be marked by hand |
| Augmented reality measuring apps (e.g. CamToPlan) | Android/iOS, free with purchases | Image/PDF depending on the app | Measure distances with the camera when there is no tape or laser | Accuracy from centimeters to decimeters; **not verified** in a primary source which formats it exports today |
| AutoCAD (DWG) | Autodesk, paid subscription; there is an electrical toolset | Native DWG, DXF, PDF | The de facto standard for firms and municipalities that ask for DWG | Paid; learning curve |
| BricsCAD | Octave (formerly Bricsys), paid; Lite (2D), Pro (2D/3D) and Ultimate, with BIM and Mechanical toolsets; Windows, Mac, Linux | Native DWG, DXF, PDF, others | DWG-compatible alternative | Paid |
| QCAD | Community Edition GPLv3, free (distributed as source code or in Linux distribution packages; the installer from qcad.org is a Professional trial); Professional paid (one-time payment); QCAD 27; Windows, Mac, Linux | DXF (Community and Professional); DWG only in Professional | Simple 2D floor plan, opening the tool's DXF files | 2D only; without Professional it does not open DWG |
| LibreCAD | GPLv2, free; Windows, Mac, Linux | Native DXF, PDF, SVG, image | Free 2D floor plan | DWG read-only and limited (**not verified** in a primary source) |
| FreeCAD | Open source (LGPL), free; version 1.1 | DXF, SVG, IFC, STEP and others | 2D/3D and BIM workbench with IFC | Heavy for a house sketch |
| draw.io / diagrams.net | Apache 2.0, free, web and desktop | PDF, SVG, PNG, editable | Simple single-line diagrams and diagrams; has "Floorplan" palettes (walls, doors, dimensions) and "Electrical" (schematics: switches, sources, instruments) | Does not include Argentine installation drawing symbols (socket outlets, outlet points): you have to build them |
| QElectroTech | GPLv2+, free; v0.100; Windows, Mac, Linux | PDF, SVG, DXF, image | Single-line diagrams and panel schematics, with a collection of more than 8000 symbols, terminal block and bill of materials | It is for schematics, not floor plans |
| Revit / BIM (IFC) | Revit paid; IFC is an open standard (buildingSMART, ISO 16739) | IFC, DWG, PDF | Large projects coordinated across disciplines | Out of proportion for surveying a house |
| `gateway electricidad plan` (this guide) | Agent tool, no cost to the person | SVG, PNG, PDF, DXF R12, Markdown | Floor plan with symbols, single-line diagram, per-circuit sheets, progress | Approximate sketch; does not replace a CAD or a signed drawing (ELEC-PLA-21) |

### ELEC-PLA-1: Choose the tool by what must be delivered, not by fashion
- **Rule:** to survey and hand out work, a hand sketch + `gateway electricidad plan` is enough. Move to CAD when
  someone requires a dimensioned DWG/DXF (municipality, firm, owners' association (*consorcio*)) and to BIM/IFC only if the
  job is already managed in BIM.
- **Why:** the goal of the survey is to know what is there and not to work on the wrong circuit; a perfect CAD drawing that
  takes a week does not help the team that goes in tomorrow.
- **How:** (1) survey by hand (ELEC-PLA-7 to 9); (2) send photos of the sketch to the agent (ELEC-PLA-17); (3) use the
  per-circuit sheets (ELEC-PLA-19); (4) if they ask for CAD, export `plan dxf` and finish it in LibreCAD, QCAD, BricsCAD or
  AutoCAD. For the formal single-line diagram (*unifilar*), QElectroTech or draw.io; for the working one, `plan single-line`.
- **Verify:** before starting, ask who will receive the drawing and in what format.
- **Don't:** buy software to survey a house; wait for the CAD before starting work.
- **Source:** official sites of each tool (see `sources`); this guide's criterion.

### ELEC-PLA-2: Exchange in open or documented formats: PDF to read, DXF to edit
- **Rule:** send PDF (or PNG by chat) to whoever has to **read** it; DXF to whoever has to **edit** it; DWG only if they ask
  for it; IFC only in a BIM workflow; SVG for the web or to reopen in a vector editor.
- **Why:** PDF opens on any phone; DXF is published by Autodesk and every free and paid CAD opens it; DWG is a proprietary
  format and its versions cause problems between programs; IFC is the open BIM standard (in IFC 4.3: `IfcOutlet` for
  socket outlets, `IfcSwitchingDevice` for switches and circuit breakers, `IfcProtectiveDevice` for MCBs and RCDs
  (*disyuntor* / *diferencial*), `IfcDistributionBoard` for panels, which replaces `IfcElectricDistributionBoard`,
  deprecated), but it requires a complete 3D model.
- **How:** `gateway electricidad plan draw F.json --format pdf` to send; `gateway electricidad plan dxf F.json`
  to edit (DXF R12 with layers ROOMS, DIMENSIONS, PANELS, one layer per circuit (CIRC_<id>), TEXT). When opening the DXF, turn off
  layers to see a single circuit.
- **Verify:** open the DXF in a viewer before sending it; the PDF has a title block with the date and the legend "Approximate sketch,
  not to scale" ("Croquis orientativo, no a escala" on a Spanish drawing) when applicable.
- **Don't:** send a new-version DWG to someone when you don't know what they will open it with; send the JSON to a person.
- **Source:** buildingSMART, IFC 4.3 (docs for IfcOutlet, IfcSwitchingDevice, IfcProtectiveDevice and deprecation note
  for IfcElectricDistributionBoard in IFC4.3.0.0); magicplan help center (DXF without dimensions). **Not verified in a primary
  source:** that IFC 4.3 is the edition published as ISO 16739-1:2024 (known fact, not checked with ISO).

### ELEC-PLA-3: What a submission requires: design project with drawings and report, with the minimum of Anexo 770-A
- **Rule:** for a dwelling (770) the minimum set by the AEA, unless the local authority asks for something else, is:
  project summary (demand, grade, floor area, circuits, cross-sections, Icc at the supply, outlet points per room),
  **single-line diagram** of each panel with the data of each device and cross-section, **drawing or sketch** with the floor
  area of each room, conduits with sizes, cables and the circuit they belong to, location and purpose of each outlet point,
  earth electrode and its conduit, and **list of materials** with brand and certification. The utility (distribution
  company, *distribuidora*) usually also asks for the load schedule (*planilla de cargas*) (ELEC-CIR-20).
- **Why:** 770.2.1 requires a prior design project with drawings and a report signed by a professional with the relevant
  competence; Anexo 770-A (mandatory) sets the minimum content.
- **How:** the survey gives you the basis for the drawing and the single-line diagram; the schedule comes from `gateway
  electricidad demand`. Before drawing the submission version, ask the utility, the municipality and the professional
  council or local body what format, scale, title sheet and copies they require (see ELEC-NOR-13 in
  [regulations-and-permits.md](regulations-and-permits.md)). For drawing sheets, the 770 refers to IRAM 4504 (formats,
  graphic elements and folding) when the authority sets nothing else.
- **Verify:** each circuit in the single-line diagram appears on the drawing with its number and each outlet point has a
  circuit (ELEC-PLA-18).
- **Don't:** submit the survey sketch as a design project; assume all utilities ask for the same thing. In the ENRE area,
  DCI option 2 for electro-dependent persons also requires a dimensioned drawing of the socket outlet (ELEC-NOR-19); for
  everything else, confirm with the utility what documentation it requires.
- **Source:** AEA 90364-7-770:2017, 770.2.1 and Anexo 770-A (770-A.1.1 to 770-A.1.4, and note to 770-A.1.2 that refers to
  IRAM 4504); EDELAR EC 1.1.13.10 v3 (2023), cited in ELEC-CIR-20. **Not verified in a primary source:** format
  requirements of specific municipalities and professional councils; they vary by jurisdiction.

## Standardized symbols

**Which standard applies.** In Argentina the symbols for residential installation drawings are those of **IRAM 2010**
(family "Símbolos gráficos electrotécnicos" (electrotechnical graphic symbols); known parts: 2010-1 kinds of current,
distribution systems and connections; 2010-3 control and protective devices; 2010-6 generation and conversion; and a
section dedicated to lighting, heating and motive power installations). It is what is taught at universities (UNCuyo, UTN)
and what any electrician recognizes. The international reference is **IEC 60617** (today an online database).
**IRAM 4504** belongs to the technical drawing series (formats, graphic elements and folding of drawing sheets), not to
electrical symbols; **IRAM 4502** is usually cited as the one for lines in that same series. In the text of **AEA
90364-7-770:2017** there is no symbols annex: its Anexo 770-D (informative, normative and regulatory references) lists
IRAM 4504 and not IRAM 2010, and the mandatory reference to IRAM 4504 is in the note to 770-A.1.2. What follows describes
the shape (the standard is not reproduced) according to the reproduction of IRAM 2010 in the UNCuyo course notes; the current
edition is bought from IRAM. **Not verified in a primary source:** that IRAM 4502 is the standard for drawing lines, and that
IRAM tends to unify its symbols with IEC 60617.
### ELEC-PLA-4: Use IRAM 2010 symbols (or IEC 60617) and put the legend on every sheet
- **Rule:** draw with the IRAM 2010 symbols the trade already knows, and put on **every** sheet a legend with the
  symbols that appear on it. If you use one of your own, it goes in the legend.
- **Why:** there are variants (old editions, IEC, design-firm habits); the legend keeps a technician from reading "toma"
  (socket outlet) where there is "boca de fuerza motriz" (motive power outlet point). The Uruguayan standard UNIT 24
  recommends the same (symbol table on every drawing).
- **How:** `plan draw` and `plan sheets` add the legend automatically with the symbols used on that sheet.
- **Verify:** no symbol on the sheet is missing from the legend.
- **Don't:** mix the IRAM socket outlet and the IEC socket outlet on the same sheet without saying so; use cartoon "plug"
  icons.
- **Source:** IRAM 2010, Sección IV (reproduced in the UNCuyo course notes, Apéndice II); IEC 60617. **Not verified in a
  primary source:** the number and title of the current part of IRAM 2010 that contains the installations section (the one
  consulted is an old edition) and the UNIT 24 citation (2019 draft, seen in a search summary).

### Table of the most used symbols

| Element | IRAM 2010 (shape described) | IEC 60617 (shape described) | How `plan` draws it (type in the JSON) |
|---|---|---|---|
| Ceiling outlet point (center) | Filled dot; with more effects, filled dot inside one or two rings | Circle with an X (lamp/luminaire) | Filled circle with circuit number and switch letter beside it (`ceiling_light`) |
| Wall light (wall outlet point, "brazo") | Filled dot on a short stroke joining it to the wall; in practice, filled semicircle with a bar against the wall | Lamp with a stroke toward the wall | Filled circle with a short stroke perpendicular to the nearest wall (`wall_light`) |
| One-way switch (*llave de un punto*) | Small empty circle with an oblique stroke ending in a small tick | Same: circle with oblique stroke and tick | Empty circle + oblique stroke with tick + letter of the effect (`switch`) |
| Two-gang switch (double) | Circle with two oblique strokes open in a V | Circle with two strokes | Circle + two strokes in a V (`double_switch`) |
| Two-way switch (*llave de combinación*, changeover) | Circle with oblique stroke and tick, with a second stroke toward the opposite side | Circle crossed by a stroke with a tick at each end | Crossed circle, tick at both ends (`two_way_switch`) |
| Socket outlet (*tomacorriente*) | Arc open downward with a vertical stroke (inverted "Y" shape) | Semicircle with a line on the straight side | Arc with stroke perpendicular to the wall (`socket`) |
| Socket outlet with earth (2P+T IRAM 2071) | Same, with a filled dot or triangle at the tip of the stroke | Semicircle with an extra parallel line (protective contact) | Arc + stroke + filled triangle. Since in Argentina all new socket outlets are 2P+T, `socket` is already drawn with earth |
| Double socket outlet | Two socket outlet symbols together | Semicircle with two strokes | Arc with two strokes and "2" (`double_socket`) |
| 20 A / special use socket outlet (TUE) | Socket outlet "for motive power or heating": filled arc | Socket outlet with type indication | Filled arc + "20A" (`socket_20a`) |
| Outdoor / protected socket outlet | "Protected" socket outlet with a dot on the arc | Socket outlet with IP rating indicated | Socket outlet + "IP" (`outdoor_socket`) |
| Junction / branch box | Square with strokes coming out (inputs and outputs); in practice, small half-filled square ("caja registro") | Small square or circle | Empty square (`junction_box`); without a device it is not an outlet point (770.6.6 note 1), except boxes in the slab up to 100 × 100 mm, which count as an outlet point (770.7.1 l). With several circuits: ELEC-PLA-25 |
| Main panel | Rectangle of 1:3 proportion crossed by both diagonals; in practice, the two opposite halves filled (bow tie) | Rectangle with designation | 1:3 rectangle with both diagonals and its id ("TP") (`panels`, without `upstream`) |
| Sub-panel (*tablero seccional*) | 1:3 rectangle with a single diagonal; in practice, half filled | Rectangle with designation | 1:3 rectangle with one diagonal and its id ("TS1") (`panels` with `upstream`) |
| Meter | "M" inside a circle or rounded-corner rectangle (meter box) | Rectangle or circle with "Wh"/"kWh" | Circle with "M" (`meter`) |
| Earth rod (*jabalina*) / earthing | Vertical stroke ending in three increasingly shorter horizontal lines | Same symbol (IEC 60417-5017) | Earth symbol with the earth electrode id (`earth_rod`) |
| Motive power or heating outlet point | Empty circle | Circle with designation | Empty circle with abbreviation: AA, TT (water heater, *termotanque*), B (pump, *bomba*), M (motor), EX (exhaust fan, *extractor*) (`ac`, `water_heater`, `pump`, `motor`, `extractor_fan`) |
| Doorbell (push button) / door entry phone | Small circle with dot (button); bell: circle over square; door entry phone: "PE" in a rectangle | Varies | Circle with dot (`doorbell`); "PE" in rectangle (`door_phone`) |
| Telephone, TV, data | "T" or "Ti" inside a circle; TV with "TV" | Varies | Circle with "T", "TV" or "D" (`tv`, `data`) |
| Sensor, emergency light | No symbol in the section consulted | Varies | Circle with "S" or "E" (`sensor`, `emergency_light`), always in the legend |
| Lighting / socket outlet line | Thin continuous line | Continuous line | Continuous line in the circuit's color (`runs`) |
| Motive power line | Thick continuous line | Continuous line | Thick line for TUE, ACU, APM |
| Signal / ELV line | Dash-dot line | Line with designation | Dash-dot for MBTF |
| Underground line | Dashed line | Dashed line | Dashed if the run's `note` says "underground" (or "subterráneo") |
| Number of conductors | Small oblique ticks crossing the line (2, 3 or 4) or the number | Oblique ticks or number | Text "2x1,5+T2,5" ("2x1.5+T2.5" on an English drawing) next to the run when there is `section_mm2` and `pe_mm2` |
| Conduit with size | Diameter above the line and conductors × cross-section below; practical example: "PVC 20" above, "2x1,5+T2,5" below (PE minimum 2.5 mm², ELEC-CON-6) | Designation next to the line | Same as the practice, if the data is in the circuit's `notes` |
| Rises / drops | Short stroke with arrow or dot indicating "upward", "from above", "downward", "from below" | Arrow | Not in the contract: write it in the point's `note` |

**Not verified in a primary source:** the shapes in the IEC 60617 column were described without consulting the IEC 60617
database; take them as guidance and confirm in the official database before using them on a drawing for submission. The
IRAM 2010 column comes from the old edition reproduced in the UNCuyo course notes (ELEC-PLA-4).

**Conduit through slab, floor or wall.** The IRAM 2010 consulted distinguishes lighting, motive power, signal and
underground lines, not "slab" or "floor". Design-firm custom is a **solid line through slab and wall, dashed line through
floor or subfloor (*contrapiso*)**, stated in the legend (usual practice, **not verified** as a clause). In the by-eye
sketch the routes are **schematic**: they join the outlet points in the order of `sequence`, they do not show where the
conduit really runs.

### ELEC-PLA-5: Identify everything: circuit number at each outlet point, letter on each switch, conduit sized
- **Rule:** each outlet point carries the **id of its circuit**; each light outlet point and its switch carry the **same
  letter** (a, b, c...); each conduit run, if known, its size and its wiring. Circuits are numbered consecutively and
  with their code (IUG1, TUG1, TUE1...). Colors, if used, are explained in the legend.
- **Why:** with that, the drawing, the single-line diagram and the panel (*tablero*) speak the same language: the technician reads
  "TUG2" on the sheet, on the panel label and at the outlet point.
- **How:** the circuit `id` in the JSON is the one seen on the drawing and on the label. Classic university convention
  (UTN FRRo): red lighting and socket outlets, blue motive power, green doorbells, yellow telephone and TV, brown door entry
  phone, black title sheet and texts. `plan draw --color circuit` assigns one color per circuit; `--color status`
  colors by progress (ELEC-PLA-20).
- **Verify:** there is no outlet point without a circuit and no switch without a letter (`plan validate` checks it; the
  letter goes in the point's `letter` field, which the tool adds to the contract).
- **Don't:** number differently on the drawing and on the panel; reuse the number of a removed circuit.
- **Source:** UTN FRRo, Castro and Juzefiszyn, "Proyecto de instalaciones eléctricas v3" (2014), section "Dibujo - normas"
  (colors, letters per switch, number per circuit); UNCuyo course notes (circuits identified with colors, dimensioned,
  numbered, letters for lights and switches); AEA 770:2017, Anexo 770-A.1.3. See ELEC-CIR-20.

## Surveying by eye on site

### ELEC-PLA-6: Before going in: look without touching, and know where to cut off
- **Rule:** before walking through, locate the meter, the main panel and all sub-panels (TS, *tablero seccional*), and check
  for other sources (generator, UPS, solar inverter, a second meter). Inspect the panel only by looking (ELEC-REV-1). If
  there is a burning smell, heat or crackling, cut off and get out: that is not a survey, it is an emergency (ELEC-REV-9).
- **Why:** in a house with leakage and short circuits there are hot boxes, bare cables and MCBs (*térmicas*) tripped for a
  reason. Knowing where to cut everything off is the first thing you need if something goes wrong.
- **How:** photo of the panel with the door open and the inner cover (dead front, *contratapa*) in place; note which MCBs
  are off and since when (ask the occupants); identify the main switch and the utility's (which is not touched,
  ELEC-NOR-15).
- **Verify:** you know where the main switch of each panel is, and so does everyone on the team.
- **Don't:** switch on tripped MCBs "to see what they feed" (ELEC-SEG-22); remove inner covers for the photo.
- **Source:** see ELEC-REV-1, ELEC-REV-9, ELEC-SEG-6, ELEC-SEG-22.

### ELEC-PLA-7: Walk-through and sketch per room, with approximate measurements and a fixed origin
- **Rule:** first a full walk-through without noting details; then a sketch **per floor**, with each room as a
  rectangle (or polygon), approximate measurements and an **origin** at the bottom left of the floor plan. State how it was
  measured.
- **Why:** the `survey.json` contract uses meters from that origin; if each room is measured "its own way",
  the outlet points end up outside the walls and the drawing does not close.
- **How:**
  1. Choose the origin (bottom-left corner of the floor in the sketch, with the entrance at the bottom if possible) and
     note north if you know it.
  2. Measure each room: **laser** (best, ± 1 cm), **tape** (good), **paces** (a normal pace ≈ 0.7–0.8 m; calibrate
     your pace by counting paces over 10 m of tape) or **floor tiles** (count and multiply by the size of one). Note which
     you used: it goes in `source` ("by-eye sketch", "measured with laser").
  3. Draw by hand, on grid paper, one small square = 0.5 m or 1 m. Doors and windows approximate (they help locate
     switches).
  4. Mark wet areas (`wet: true`): bathroom, laundry, semi-covered area, outdoors or any area that gets hosed down. The
     kitchen is a judgment call (for example, if it gets hosed down or the countertop is right next to the sink) and the
     reason is stated in the `note` of its socket outlets. The field serves to warn about socket outlets without an RCD
     (*disyuntor* / *diferencial*, ID) in wet areas; the 30 mA ID is required anyway on all final circuits (ELEC-PRO-7),
     and the rules for outdoor and exposed locations are in ELEC-CIR-11.
- **Verify:** the sum of adjoining rooms gives the total length of the house within a reasonable error (about 10 %).
- **Don't:** waste time on centimeters when the goal is to locate outlet points; mix floor plans on the same sheet.
- **Source:** this guide's criterion; `survey.json` contract (coordinates in meters, origin bottom-left).

### ELEC-PLA-8: Number each outlet point and photograph it with its number
- **Rule:** each outlet point, switch, junction box and panel gets a unique id (p1, p2... or per room, coc1, coc2...),
  written on the sketch and photographed **with the number visible** (masking tape or a post-it on the cover plate,
  without taking anything apart).
- **Why:** the photo with the number avoids arguments ("which kitchen socket outlet?") and lets the agent and the
  technician confirm the type of outlet point without going back.
- **How:** one general photo of the room with all the numbers and a close-up of each outlet point. Name the photos or send
  them in order by chat with their id. Always go around in the same direction (clockwise from the door).
- **Verify:** every id on the sketch has a photo and vice versa.
- **Don't:** remove socket outlet or switch cover plates to photograph the inside while live; write on the wall with a
  marker.
- **Source:** this guide's criterion; Res. SRT 900/2015, instructions items 15 and 22 (sketch with numbered points that
  match the measurement, same principle).

### ELEC-PLA-9: What to record for each outlet point, each panel and each protective device
- **Rule:** record what you see, mark what is not known as `unverified` and don't fill in with what is
  likely.
- **Why:** a "likely" value that stays written down is later read as measured: someone chooses a protective device or
  takes a circuit as safe with a value nobody checked.
- **How:**

  | Element | Data |
  |---|---|
  | Outlet point | id, type (symbol table), room, approximate position (x, y), height, visible condition (burnt, loose, no cover plate, no earth), circuit if already known, letter of the switch that controls it (`letter`) |
  | Panel | id, name, location, which panel it comes from (`upstream`), photo of the front |
  | Protective device | id, type (MCB, RCD, RCBO, SWITCH, FUSE, SPD, MPCB), poles, In, curve, breaking capacity (kA), IΔn and class of the ID, written label, position (up/down, if it was tripped) |
  | Circuit | code and name, protective device, cross-section if it can be read, who it is assigned to, status |
  | General | supply type (single/three-phase), voltage, date, how it was measured, job (short text **without** name or address) |

- **Verify:** no cross-section, earth or ID status value appears as "ok" without having been measured (ELEC-REV-2).
- **Don't:** put the owner's name, DNI (national ID number), address or phone number in the JSON or on the drawing (the
  `job` field is a short text, e.g. "back-house").
- **Source:** `survey.json` contract; ELEC-REV-2, ELEC-REV-5, ELEC-REV-6.

### ELEC-PLA-10: Heights: record the real one; the standard gives references for socket outlets
- **Rule:** record the measured height of each wall outlet point (`height_m`). As a reference, the 770 requires
  skirting-level socket outlets with the bottom edge of the box at 0.20–0.30 m from the floor, countertop socket outlets at
  no less than 0.10 m above the countertop, and in hosed-down areas at 0.30 m or more. A socket outlet on the lighting
  circuit cannot be lower than 0.90 m. An **outlet point** (box with a socket outlet or fitting) can also serve as a junction
  or branch box for more than one circuit only if it is at 1.80 m or more; junction and branch boxes without a device are
  not outlet points and the note sets no height for them.
- **Why:** the height tells a countertop socket outlet from a skirting one, flags badly placed socket outlets and helps the
  technician suspect high outlet points (wall lights, outlet points at 1.80 m or more) that may carry conductors of other
  circuits. Any box, high or low, can carry them (ELEC-PLA-16, ELEC-PLA-25).
- **How:** with a tape from the finished floor to the bottom edge of the box. Switches and wall lights have no mandatory
  height in the 770; the custom is switches at 1.10–1.20 m and wall lights at 1.80–2.10 m (practice, not standard).
- **Verify:** socket outlet below 0.90 m marked as on the lighting circuit → warning (ELEC-CIR-8).
- **Don't:** invent "typical" heights to fill in the JSON: if it was not measured, leave it empty.
- **Source:** AEA 90364-7-770:2017, 770.7.2 (heights of socket outlets, countertops, hosed-down areas); 770.6.6 note 1 b) (an
  outlet point can also be a junction or branch box for more than one circuit if it is at no less than 1.80 m); 770.7.1 m)
  (socket outlets connected to the lighting circuit are not allowed at less than 0.90 m from the floor; mixed outlet points
  identified with the symbol IEC 60417-5012), as cited in ELEC-CIR-8. Heights of switches and wall lights: **not verified in
  a primary source** (usual practice).
## Mapping circuits without risk

### ELEC-PLA-11: One MCB (*térmica*) at a time, with the rest on, walking around with a plug-in tester
- **Rule:** switch off **one** MCB (*térmica*) at a time, with the others on, and walk through the house testing each
  socket outlet with a plug-in tester (or a lamp with a plug) and operating each switch. What went off **belongs** to that
  MCB, but that does not mean it is now **dead** (ELEC-PLA-16). Switch it back on and go on to the next one. While the
  mapping lasts, nobody works in boxes or in the panel (*tablero*) (ELEC-PLA-13).
- **Why:** switching everything off and turning them on one at a time mixes up the results when there are circuits coming
  from another panel or shared neutrals; switching off one at a time shows exactly what depends on each device. And it is
  done without opening anything.
- **How:**
  1. Warn the occupants: fridge, computers, alarm, gate, pump and medical equipment (electro-dependent persons: **do not
     cut off** without agreeing on an alternative source).
  2. RCDs (*disyuntor* / *diferencial*, ID) first: switch off each RCD and note which MCBs lose supply downstream (this
     builds the CG → ID → PIA tree of the single-line diagram).
  3. Then each PIA: switch one off, walk around and note on the sketch the circuit of each outlet point (*boca*). Socket
     outlets: plug-in tester with lights (it gives a hint about reversed phase and neutral or missing earth). Lights:
     operate each switch with a working lamp. The tester does **not** replace PE continuity (ELEC-MED-3): it does not
     detect a PE bridged to the neutral at the socket outlet (it shows "ok") or a high-resistance PE, so the earth stays
     `unverified` until it is measured. Don't plug anything into burnt, loose or heat-marked socket outlets: they stay
     `fault` or `unverified`. Note the single-pole protective devices (`poles: 1`): those are the ones that can turn off
     the outlet point and leave the phase (ELEC-PLA-16).
  4. Ceiling outlet points without a lamp, boxes without a fitting, AC, water heater: they stay `unverified`
     until someone with lockout/tagout (LOTO) measures them (they are not opened live).
  5. **Circuits that cannot be energized** (the MCB trips, there is leakage or a short circuit): they are mapped **dead**.
     The installation or the section is locked out (ELEC-SEG-3, 4, 5) and a technician identifies by continuity (ohmmeter
     between a conductor and a temporary jumper at the panel) or with a tone generator in dead mode. Conditions: (a) the
     circuit's conductors are disconnected from their PIA and from the neutral terminal block and separated, because
     otherwise continuity passes through loads and shared neutrals and gives false positives; (b) the jumper carries a tag
     and is noted in the circuit's `notes`; (c) it is removed and checked that it is gone before re-energizing: a forgotten
     jumper is a dead short circuit on energizing, with someone in front of the panel (ELEC-SEG-7, Decreto 911/96 art. 79
     c); (d) while identifying, nobody works in boxes of that circuit or in boxes it shares; if insulation testing is done,
     ELEC-EQU-27 applies. This is a technician's job, not the person's.
- **Verify:** at the end, each MCB has at least one outlet point and each outlet point has a circuit or `unverified`;
  MCBs that turned nothing off are noted (unused circuit, from another panel or mislabeled).
- **Don't:** switch on an MCB that tripped to "see what it fed" (ELEC-SEG-22); use this method as verification of absence
  of voltage for working (ELEC-PLA-16); map with a screwdriver-type voltage tester (*buscapolo*).
- **Source:** usual circuit identification practice, **not verified in a primary source** as a standardized procedure.
  Dead work and lockout/tagout: Decreto 351/79 Anexo VI item 1.1.4; Decreto 911/96 arts. 78-79 (see ELEC-SEG-2 to 5).
  Diagnosis of leakage per circuit: ELEC-DIA-2, ELEC-DIA-4.

### ELEC-PLA-12: The circuit finder helps, but confirm by switching off
- **Rule:** a breaker finder (transmitter that plugs into the socket outlet and receiver passed along the front of the
  MCBs) serves to speed things up; the result is confirmed by switching off that MCB and seeing the socket outlet go off.
- **Why:** the signal couples into neighboring cables and adjacent MCBs; with old wiring, shared neutrals or circuits that
  run through the same conduit, the receiver points to the wrong one.
- **How:** use a device for 220–240 V (many models sold online are for 120 V only: check the rating plate). Connect
  the transmitter to the socket outlet; for light outlet points there are lampholder adapters. Pass the receiver slowly
  over all the MCBs, keep the one with the strongest signal and confirm by switching it off. In dead mode (tone generator),
  only with the circuit locked out.
- **Verify:** confirmation by switching off noted on the sketch.
- **Don't:** rely on the finder to choose which MCB to lock out before working; connect transmitters between phase and
  earth in an installation with an RCD (they can make it trip). Only instruments with a suitable category (ELEC-SEG-13).
- **Source:** operating principle of commercial finders (transmitter-receiver). **Not verified in a primary source:**
  the coupling limitations and the warning about RCD (ID) tripping, which are trade practice; the manufacturers' sheets
  (Fluke, Klein) could not be consulted.

### ELEC-PLA-13: In pairs, with a handheld radio or phone, and only one person operates the panel
- **Rule:** one person at the panel (operates **only** what is asked and confirms out loud), another walking around.
  They communicate by handheld radio (*handy*) or an open call. Every operation is announced **before** it is done.
- **Why:** shouting from one floor to another ends in "which one did you switch off?" and in MCBs switched on with
  someone's hands in a box.
- **How:** short protocol: "Bajo C3" (switching it off) → "Bajado C3" (switched off) → walk-through → "C3 listo, subí" (done,
  switch it on) → "Subido C3" (switched on). The person at the panel notes the time and the state of each device. If the person
  walking around sees something odd (spark, smell), they say "corto todo" (cutting everything) and the person at the panel
  switches off the main switch.
- **Verify:** at the end, the state of the panel matches the initial photo (except what was left off on purpose, with a
  tag).
- **Don't:** let two people operate the same panel; combine the mapping with work in progress. Live mapping is an
  **exclusive phase**: while it lasts, nobody opens boxes, cover plates or the panel anywhere in the installation, not even
  with their circuit locked out, because conductors, neutrals or switch returns of the circuit being switched on and off
  may pass through their box (ELEC-PLA-16). The occupants don't touch the panel or the MCBs either: they are told
  beforehand and the panel is signposted (ELEC-EQU-28). Only when the mapping is finished, with the panel in the agreed
  state, does work under lockout/tagout begin (ELEC-PLA-24).
- **Source:** this guide's criterion; for work under lockout/tagout, ELEC-SEG-4 and ELEC-SEG-7 (each person their own
  padlock); ELEC-EQU-16 (closed phrases) and ELEC-EQU-28 (occupied house).

### ELEC-PLA-14: Label on the spot, temporary first and permanent at the end
- **Rule:** when a circuit is identified, label it **at that moment** with masking tape and the circuit id
  ("TUG2 coc+lav"); the permanent label (printed, indelible) goes on when the circuit is verified.
- **Why:** old labels often lie (ELEC-REV-19); a new temporary one that matches the drawing avoids carrying the error
  forward.
- **How:** id the same as in the JSON and on the drawing. The previous label is recorded in the protective device's
  `label` (it serves as history) and covered or removed.
- **Verify:** label = drawing = single-line diagram, device by device.
- **Don't:** leave two labels that contradict each other; write on the inner cover (dead front, *contratapa*) with a
  marker.
- **Source:** ELEC-TAB-8, ELEC-TAB-18, ELEC-REV-19.

### ELEC-PLA-15: Suspect shared neutrals, circuits from another panel and outlet points that never go off
- **Rule:** an outlet point that does not go off with any MCB, one that goes off with two different ones, an RCD that
  trips when a load is switched on in a circuit that depends on another RCD (or two RCDs that trip together), or a light
  that stays "ghost" dimly lit, are signs of crossed wiring (neutral crossed between RCDs: ELEC-TAB-16, ELEC-DIA-5). They
  are recorded as `fault` or `doubtful` and resolved dead.
- **Why:** with a neutral shared between circuits, switching off an MCB does **not** kill the neutral: it keeps carrying
  the current of the other circuit. An outlet point that comes from another panel (from another apartment (*depto*), from
  common services, from an old meter) stays live even if the house panel is all switched off.
- **How:** mark those outlet points on the sketch (`status: doubtful`, `note: "does not go off with any MCB"`), look for other
  panels or meters, and pass the case to diagnosis ([troubleshooting-common-cases.md](troubleshooting-common-cases.md),
  ELEC-DIA-5, ELEC-DIA-14).
- **Verify:** before working on one of those outlet points, two-pole voltage tester between all pairs (ELEC-SEG-5).
- **Don't:** assume that "with the main switch off there is nothing"; separate neutrals live.
- **Source:** ELEC-DIA-5, ELEC-TAB-16, ELEC-REV-16, ELEC-SEG-1.

### ELEC-PLA-16: Never open a box live to see where it comes from; the map is not a verification
- **Rule:** no box, socket outlet or switch cover plate, junction box or inner cover is opened live during the survey.
  And the map saying "this outlet point is on C3" does **not** replace locking out and verifying absence of voltage in
  that box before touching it.
- **Why:** mapping with a tester shows what stops **working**, not what is **dead**: a shared neutral, a two-way switch
  return from another circuit or a cable from another panel can pass through the same box. A single-pole MCB placed on the
  neutral (phase and neutral reversed in the panel), or a switch that cuts the neutral, turns off the outlet point but
  leaves the phase in the box (ELEC-DIA-15, ELEC-EQU-24). Any junction box can carry several circuits, and an outlet point
  at 1.80 m or more can also be a junction box for several (770.6.6 note 1 b).
- **How:** to open: full lockout/tagout (ELEC-SEG-3), lockout with padlock and tag (ELEC-SEG-4) of the device that
  applies according to the phase of the job (ELEC-PLA-24), verification with a two-pole voltage tester checked before and
  after on a known source (ELEC-SEG-5), **in the box**, between all conductors and to earth, including those of other
  circuits passing through (ELEC-EQU-25).
- **Verify:** the work sheet says "verify absence of voltage IN EVERY BOX before opening it" as a
  mandatory step (ELEC-PLA-19).
- **Don't:** "I'll open the cover carefully, I won't touch anything"; pull on a cable to see which box it moves in.
- **Source:** Decreto 351/79 Anexo VI item 1.1.4; Decreto 911/96 arts. 78-79; Res. SRT 3068/2014 (live work only with
  specific authorization); AEA 770:2017, 770.6.6 note 1. See ELEC-SEG-1 to 5, ELEC-DIA-15, ELEC-EQU-24 and 25.

## From sketch to drawing with the agent

**The workflow.**
1. The person or the technician **describes or photographs** the sketch, the numbered outlet points and the panel.
2. The agent builds `/workdir/electricidad/<job>/survey.json` (ELEC-PLA-17). The person does not write JSON.
3. `gateway electricidad plan validate` → errors are corrected and warnings are read (ELEC-PLA-18).
4. `plan draw` (floor plan), `plan single-line` (panels), `plan dxf` (for CAD).
5. `plan sheets --tech NAME` → one sheet per circuit or per technician; the person in charge confirms what is locked
   out according to the phase of the job (ELEC-PLA-24) and the agent sends them by Telegram (ELEC-PLA-19).
6. Each piece of progress or measurement is entered with `plan status`; `plan summary` shows how it is going
   (ELEC-PLA-20).

| Command | What it does |
|---|---|
| `gateway electricidad plan new JOB [--dir DIR] [--lang es\|ru\|en]` | Creates `/workdir/electricidad/JOB/survey.json` (or `DIR/JOB/survey.json`) with a minimal template |
| `gateway electricidad plan validate F.json` | Errors and warnings with the ELEC-... rule that applies (list in ELEC-PLA-18); exits with code 1 if there are errors |
| `gateway electricidad plan draw F.json [--floor PB] [--color circuit\|status] [--only C1,C2] [--format svg\|png\|pdf] [--out DIR] [--lang es\|ru\|en]` | Floor plan with rooms, approximate dimensions, symbols, routes, legend and title block; `--only` dims the rest |
| `gateway electricidad plan single-line F.json [--panel TP] [--format ...] [--out DIR] [--lang ...]` | Single-line diagram of each panel (or of one): main switch → RCD → MCB → circuit with In, curve, IΔn, class and cross-section |
| `gateway electricidad plan sheets F.json [--tech NAME \| --circuit C1,C2] [--format ...] [--out DIR] [--lang ...]` | Sheet per circuit, per technician or for the requested circuits: isolated drawing, table of outlet points, protective device to lock out, pending measurements, safety checklist (PDF/PNG + Markdown) |
| `gateway electricidad plan dxf F.json [--floor PB] [--out DIR] [--lang ...]` | DXF R12 with layers ROOMS, DIMENSIONS, PANELS, TEXT and one per circuit (CIRC_<id>), for LibreCAD, QCAD, BricsCAD, AutoCAD |
| `gateway electricidad plan status F.json ID STATUS [--tech X] [--note TEXT]` | Changes the status of a circuit (or of a point); `--tech` also becomes the `assigned_to`; the note is appended to `notes` with the date; `.bak` copy and atomic write |
| `gateway electricidad plan summary F.json` | Progress by circuit, technician and status |
| `gateway electricidad plan symbols [--lang ...]` | The symbols it draws, with name and source |

Every subcommand also takes `--json` (English keys, for the agent). `F.json` can be the path or the job name (it looks
for `$ELECTRICIDAD_DIR/JOB/survey.json`, by default `/workdir/electricidad/JOB/survey.json`). The outputs go to
`/workdir/electricidad/<job>/output/` (or to `--out`, which must stay inside the job folder). The SVG is always produced;
PNG (default format) and PDF are generated with typst, rsvg-convert, ImageMagick or Inkscape, whichever is found first; if
there is none, the SVG remains and the tool warns. `--lang es|ru|en` sets the language of the text a person reads on
drawings and sheets; without it, the `lang` in the prefs file (`$AIBRIDGE_PREFS`), else es. What the tool prints and its
`--json` are always in English. Besides the contract fields, the tool reads `letter` in the points (letter of the switch
and of its outlet points, ELEC-PLA-5) and `north_deg` at the root, and `plan status` writes a `log` with each change
(date, id, from, to, tech and note).

### The `survey.json` contract

One file per job. Coordinates in **meters**, origin at the bottom left of each floor; approximate values are fine. What is
not known is left out or written as `"illegible"`, never guessed. Full example:
`/usr/local/share/aibridge/electricidad/examples/house-panel-photo.json`.

```json
{
 "version": 1, "job": "short text, no names or addresses", "source": "by-eye sketch | existing drawing | measured with laser",
 "date": "YYYY-MM-DD", "north_deg": 0,
 "supply": {"type": "single_phase|three_phase", "voltage_v": 220},
 "floors": [{"id": "PB", "name": "Ground floor"}],
 "rooms": [{"id": "coc", "name": "Kitchen", "floor": "PB", "polygon": [[0,0],[3.5,0],[3.5,3],[0,3]], "wet": false}],
 "panels": [{"id": "TP", "name": "Main panel", "floor": "PB", "x": 0.2, "y": 2.5, "upstream": null}],
 "devices": [
   {"id": "CG", "panel": "TP", "type": "MCB|RCD|RCBO|SWITCH|FUSE|SPD|MPCB", "poles": 2, "in_a": 40, "curve": "C", "icn_ka": 4.5,
    "idn_ma": null, "class": null, "upstream": null, "label": "TERMICA GRAL"},
   {"id": "ID1", "panel": "TP", "type": "RCD", "poles": 2, "in_a": 40, "idn_ma": 30, "class": "AC|A|F|B", "upstream": "CG"},
   {"id": "C1", "panel": "TP", "type": "MCB", "poles": 2, "in_a": 10, "curve": "C", "upstream": "ID1", "label": "ILUM COCINA"}],
 "circuits": [{"id": "IUG1", "type": "IUG|TUG|IUE|TUE|ACU|MBTF|APM|OTHER", "name": "Kitchen lighting", "device": "C1",
   "section_mm2": 1.5, "pe_mm2": 2.5,
   "status": "not_surveyed|surveyed|measured|fault|under_repair|repaired|verified", "assigned_to": "Technician A", "notes": "",
   "measurements": [{"date": "YYYY-MM-DD", "type": "insulation|pe_continuity|rcd_trip|voltage", "value": 120, "unit": "MOhm", "ok": true}]}],
 "points": [{"id": "p1", "type": "ceiling_light|wall_light|switch|double_switch|two_way_switch|socket|double_socket|socket_20a|outdoor_socket|junction_box|ac|water_heater|pump|motor|door_phone|doorbell|tv|data|sensor|emergency_light|extractor_fan|earth_rod|meter",
   "floor": "PB", "room": "coc", "x": 1.2, "y": 0.3, "height_m": 0.3, "circuit": "TUG1", "letter": "a",
   "status": "ok|fault|doubtful|unverified", "note": ""}],
 "runs": [{"circuit": "TUG1", "sequence": ["TP", "p1", "p2"], "note": ""}]
}
```

What `validate` requires (error if missing): `version` 1; at least one floor; ids present and unique across rooms,
panels, devices, circuits and points (floors have their own); every `floor`, `room`, `panel`, `upstream`, `device` and
`circuit` that is filled in points to something that exists (a panel's `upstream` can be a device or another panel); each
room's `polygon` with 3 or more vertices and an area; each device's `panel`; each circuit's `device`, which must give
overcurrent protection; each point's x, y; each run's elements are panels or points; no cycle in `upstream`. The value
lists above are the only ones it knows: another `type` or `status` is a warning. A missing `job`, `supply.type`,
`section_mm2`, panel x, y, RCD `idn_ma` or `class`, or device `in_a` is a warning. A run's `note` with "underground" (or
"subterráneo") draws it dashed.

`letter` links a switch with the outlet points it controls (ELEC-PLA-5). `plan status` adds `log` (date, id, from, to,
tech, note) and you never need to write it by hand. `plan symbols` lists the point types it draws.
### ELEC-PLA-17: The agent builds the survey.json; it asks for what is missing and does not invent
- **Rule:** the agent turns the sketch (*croquis*), the photos and what people tell it into the `survey.json` schema; what it
  does not know it leaves empty or as `not_surveyed`/`unverified`, and it asks. It never fills in cross-sections, heights or IΔn
  "out of habit".
- **Why:** the JSON is the source of the work sheets; an invented value ends up on a sheet that tells someone to lock out
  the wrong MCB (*térmica*).
- **How:** the agent asks, in this order: (1) floors and rooms with approximate dimensions, and which ones are wet;
  (2) panels (distribution boards, *tableros*) and where each one is fed from; (3) protective devices read from the front (ELEC-REV-5, 6); (4) outlet points (*bocas*) per room
  with type and position ("toma a 1 m de la puerta, pared de la izquierda, a 0,30 m", socket outlet 1 m from the door, left-hand wall, at 0.30 m); (5) which MCB turns off each outlet point
  (ELEC-PLA-11). Positions estimated "by eye" are converted to meters from the origin; `source` says how they were measured. If you
  were only given counts per room ("2 tomas y una boca", 2 socket outlets and one outlet point), the contract still requires x, y: place them in a typical spot, with
  `"status": "unverified"` and `"note": "assumed position"`, and ask for the real position when you show the draft.
- **Verify:** after building it, the agent shows a `plan draw` and asks the person to confirm "¿así es
  la casa?" (is this the house?) before generating sheets.
- **Don't:** put personal data in `job`; mix two jobs in one file; edit the JSON by hand while someone else
  is using `plan status` (always use the tool).
- **Source:** `survey.json` contract; ELEC-REV-2 (seen / deduced / not verifiable).

### ELEC-PLA-18: Validate before drawing and before handing out sheets
- **Rule:** no sheets are handed out with `plan validate` errors; warnings are read and either resolved or explicitly
  accepted. The drawing, the single-line diagram and the DXF can be generated with errors, as a **draft** so the person
  can confirm "¿así es la casa?" (is this the house?) (ELEC-PLA-17): the tool draws them and reports how many errors there are; the agent says so when
  sending them. The sheets cannot.
- **Why:** a point with no circuit is an outlet point nobody will check; a circuit with no 30 mA RCD (*disyuntor* / *diferencial*, ID) upstream is a
  risk for the technician and the user that should be visible on the sheet.
- **How:** checks that `validate` runs (`electricidad_plan.py`, version of 2026-11-15) and the rule each one cites:

  | Check | Type | Rule |
  |---|---|---|
  | Missing or duplicate ids | Error | ELEC-PLA-5 |
  | Broken references (nonexistent floor, room, panel, protective device, circuit or point), cycle in `upstream`, `version` other than 1 | Error | `survey.json` contract |
  | Point with no circuit (except junction box, meter, earth rod, door entry phone, TV, data) | Warning | ELEC-PLA-5 |
  | Switch with no `letter` | Warning | ELEC-PLA-5 |
  | Point with no x, y, or on a different floor from its room | Error | ELEC-PLA-7 |
  | Point more than 0.3 m outside its room | Warning | ELEC-PLA-7 |
  | Circuit with no protective device, or hanging from a device with no overcurrent protection | Error | ELEC-PRO-1 |
  | Circuit with no 30 mA RCD upstream (`no_rcd30`); if there is an RCD but no IΔn entered, you get `rcd30_unconfirmed`: it is missing data, resolved by reading the rating plate or testing, never by entering 30 mA blindly | Error | ELEC-PRO-7 |
  | Socket outlet in a `wet` room (or `outdoor_socket`) with no 30 mA RCD (`wet_socket_no_rcd`) | Error | ELEC-PRO-7 (ELEC-ESP-4, ELEC-CIR-11) |
  | MCB larger than the cable's Iz (table 770.12.I, B1) or than the cap for the circuit type | Error | ELEC-PRO-4, ELEC-CIR-5 |
  | Cross-section smaller than the minimum for the type | Error | ELEC-CON-5 |
  | Cross-section not entered: the MCB cannot be checked | Warning | ELEC-REV-11 |
  | PE smaller than 2.5 mm² | Warning | ELEC-CON-6 |
  | More outlet points than the cap for the type (more than 15 is an error; a TUE with 13 to 15 is a warning, because the 771 allows 12 and the 770, 15). Switches, junction boxes, earth rod, meter, TV and data do not count | Error / Warning | ELEC-CIR-5, ELEC-CIR-6 |
  | RCD with no IΔn or no class; many circuits on one RCD; RCD In lower than the sum of its MCBs; class AC RCD with motors; fuse as circuit protection | Warning | ELEC-REV-6, ELEC-PRO-9, ELEC-REV-10, ELEC-PRO-10, ELEC-PRO-20 |
  | Circuit `under_repair` with no technician assigned | Warning | ELEC-EQU-14, ELEC-PLA-20 |
  | `verified` without insulation and PE continuity ok, or with a bad measurement or outlet points in fault | Warning | ELEC-PLA-20, ELEC-MED-16 |
  | Route that passes through a point of another circuit (`mixed_run`: "shared box or common neutral?"); route that does not start at a panel | Warning | ELEC-PLA-15, ELEC-PLA-5 |

  **Which regulation applies.** The caps depend on the type of premises (ELEC-NOR-3, ELEC-CIR-1): 770 for a single-family house
  up to 63 A (BA2, BD1) if the designer adopts it and the jurisdiction accepts it; 771 for apartments, offices, shops
  and dwellings outside that scope; 772 for common services in buildings. The `survey.json` contract has no
  field to state it, and `validate` uses the cap of 15 with a warning for the TUE from 13. If the job is not a
  770 dwelling, the agent applies the 771 caps and records it in `notes` of the affected circuits.

  **What `validate` does not check and the agent checks before handing out sheets.** Several of these points decide what gets
  locked out (ELEC-PLA-19, ELEC-PLA-24):

  | Check | Consequence | Rule |
  |---|---|---|
  | Circuit protective device with `poles: 1` or not entered, or chain up to the panel with no double-pole disconnection | The sheet locks out the main switch (the printed sheet already adds it if `poles` is 1 or missing; the single-line diagram draws "?" instead of tick marks) | ELEC-EQU-24, ELEC-PRO-1 |
  | Neutral shared, crossed or not checked | Recorded in `notes` with the word "neutral" (or "neutro") (the printed sheet then adds the lockout of the main switch) | ELEC-PLA-15, ELEC-EQU-5, ELEC-EQU-24 |
  | Circuit with `doubtful` or `unverified` points | The sheet locks out the main switch | ELEC-PLA-16, ELEC-EQU-24 |
  | A shared box (mixed-route warning) between circuits assigned to different technicians | Those circuits go into a single package with a single assignee, or are separated first | ELEC-EQU-8, ELEC-PLA-25 |
  | `verified` without an RCD trip with a tester | Goes back to `repaired` until measured | ELEC-PLA-20, ELEC-MED-6 |
  | Socket outlet on the lighting circuit lower than 0.90 m | Corrected or moved to the socket-outlet circuit | ELEC-CIR-8 |
  | Out-of-range measurement marked `ok: true` | The `ok` is corrected | ELEC-MED-16 |
  | Boxes in the slab up to 100 × 100 mm (they count as an outlet point; the JSON does not hold their size) and socket outlets mounted on the panel (up to 4 on the same circuit = 1 outlet point) | The outlet-point count is adjusted by hand | ELEC-CIR-6 |

- **Verify:** `validate` with no errors; each accepted warning has a note on the circuit; the second table reviewed
  before generating sheets.
- **Don't:** clear a warning "because it is annoying" by removing the data from the JSON.
- **Source:** AEA 770:2017, 770.1 (scope: single-family house up to 63 A; offices and shops stay under the 771),
  770.6.6 a) and b) and table 770.6.I (caps of 15 outlet points in IUG, TUG and TUE; maximum protection 16, 20 and 32 A), 770.6.6 note 1
  (what an outlet point is), 770.7.1 l) (boxes in the slab up to 100 × 100 mm count as an outlet point), 770.7.2 (up to 4 socket outlets on the same
  circuit on the panel = 1 outlet point); AEA 771:2006, table 771.7.I (TUE: 12 outlet points), per ELEC-CIR-5; ELEC-EQU-8 and
  ELEC-EQU-24 for the safety checks; ELEC-PRO and ELEC-CIR rules cited.

### ELEC-PLA-19: One isolated sheet per circuit, with the protective device to lock out and the lockout (*consignación*) written down
- **Rule:** each technician receives only the sheet for their circuit (or circuits), with: floor plan with that circuit
  highlighted and the rest dimmed, table of outlet points (id, type, room, height, status), **the protective device to lock out** and the
  panel where it is, pending measurements and the lockout/tagout (LOTO, *consignación*) checklist.
- **Why:** whoever works on one circuit does not need to see the other 14; what they need is to know what to lock out, which
  outlet points are theirs and what is still to be measured. That way several people work in parallel without getting in each other's way (team organization in
  [teamwork-and-rehabilitation.md](teamwork-and-rehabilitation.md)).
- **What gets locked out.** The sheet prints the circuit's protective device (field `device`), but what gets locked out depends on
  the job phase (ELEC-PLA-24) and on the safety checks in ELEC-PLA-18. If the protective device is single-pole, the
  neutrals are not checked, there are doubtful points or the circuit shares a box with another package, the
  **main switch** is locked out with a group lockout (ELEC-EQU-24, ELEC-EQU-20). The person in charge (*responsable*) writes it on the sheet (and in `notes` of the
  circuit) even if the tool prints the PIA. They also write on the sheet the job phase and their own name as
  person in charge; the `survey.json` contract has no fields for that.
- **How:** `gateway electricidad plan sheets F.json --tech "Technician A"`. The printed sheet carries a summarized checklist
  (with the main-switch lockout added if the protective device is single-pole or `notes` mentions a neutral). The checklist that
  each technician must follow is this one; whatever the sheet does not say, the person in charge fills in by hand:
  1. Lock out what the sheet indicates (the circuit's double-pole PIA, or the main switch if the sheet says CG) with a DIN rail
     lockout device, personal padlock and tag. If the lockout device does not fit that lever, lock out an upstream device that
     can be locked (ELEC-EQU-23, ELEC-EQU-21).
  2. If the disconnection protects several people: group lockbox or lockout hasp, with one personal padlock per
     person (ELEC-EQU-20).
  3. Sources that can come back (photovoltaic, UPS, generator set, second meter) switched off and locked out, according to the
     job's list (ELEC-EQU-26, ELEC-PLA-6). The temporary supply for essential service stays live on purpose: labeled and
     with no connection at all to what is being worked on (ELEC-EQU-9).
  4. If the panel has to be opened: the incoming terminals of the incoming switch and the incoming line stay live even if the
     incoming switch is open. Disconnect and lock out at the upstream panel if there is one; if not (main panel of a
     dwelling, upstream is the utility (distribution company, *distribuidora*), which is not touched), cover the incoming terminals with a shield or
     cap and do not work on them (ELEC-SEG-28, ELEC-TAB-28).
  5. Tester checked on a known source; verify absence of voltage **in each box before touching**, between
     all conductors and to earth, including neutrals and other cables passing through; tester checked again
     (ELEC-SEG-5, ELEC-EQU-25). Cables from another circuit are treated as live (ELEC-PLA-16).
  6. Insulation test only in the window set by the person in charge, with notice and confirmation from everyone, and wait for the instrument
     to discharge (ELEC-EQU-27). PE continuity with no voltage. Enter each value with date and who measured it
     (ELEC-PLA-20, ELEC-MED-3, ELEC-MED-4).
  7. When finished: leave conductor ends insulated and boxes covered, remove **only** your own padlock and tell the
     person in charge. The technician does not switch anything on: the person in charge energizes, with all padlocks removed and the people counted
     (ELEC-EQU-17, ELEC-SEG-7).
- **Verify:** the protective device on the sheet matches the panel label and the confirmed disconnection (ELEC-PLA-11), and
  what it says "is locked out" is consistent with the phase and with the checks in ELEC-PLA-18.
- **Don't:** work with someone else's sheet; take the sheet as proof that the circuit is dead; lock out only the
  PIA of a circuit whose neutral has not been checked.
- **Source:** ELEC-SEG-3 to 7, ELEC-SEG-28, ELEC-TAB-28; ELEC-EQU-17, 20, 21, 23 to 27; ELEC-MED-3, ELEC-MED-4, ELEC-MED-14;
  Decreto 911/96 art. 79 (lockout, verification on site, re-energizing by the person in charge); this guide's criterion
  for the content of the sheet.

### ELEC-PLA-20: Each step forward is entered with `plan status`; what was measured, with its value
- **Rule:** each circuit goes through statuses (`not_surveyed` → `surveyed` → `measured` → `fault` / `under_repair` →
  `repaired` → `verified`) and each change is recorded with who and a note. **`repaired` does not mean "it can be switched on now"**:
  it means "ready for the person in charge to energize". Only the person in charge energizes (ELEC-EQU-17), with insulation
  measured and good (Decreto 911/96 art. 79 c), all the package's padlocks removed and the people counted; the note in
  `plan status` says who energized (careful: `--tech` changes the `assigned_to`; the name of the person in charge goes in the note).
  `verified` requires insulation, PE continuity and RCD trip with a tester (ELEC-MED-6) entered and ok.
- **Why:** with several technicians, the schedule kept in one person's head gets lost; the status in the JSON lets you see at a
  glance what is missing and color the drawing by progress. If `repaired` is read as "switch it on", someone energizes on top of a
  colleague who is still in a shared box.
- **How:** `gateway electricidad plan status F.json TUG2 under_repair --tech "Technician B" --note "box coc2
  burnt"`. Measurements (insulation in MΩ, PE continuity, RCD trip, voltage) go in `measurements` with
  date, value, unit and `ok`. The `measurements` schema has no field for who measured: it is recorded in the note of the
  status change or in `notes` of the circuit ("insulation 2026-11-15: Technician B"), as ELEC-EQU-27 requires. `plan summary`
  builds the progress table; `plan draw --color status` the floor plan.
  **Partial re-energizing with others working:** only if the circuit being energized is in an independent package
  (its own double-pole disconnection, neutrals checked, no boxes shared with another package in progress, ELEC-EQU-8). The
  person in charge tells everyone, counts the people and energizes. Live tests (RCD trip, voltage at socket outlets) are
  done by them or by someone they designate, with an instrument of suitable category (ELEC-SEG-13). If this is not met, energize at the end,
  with the whole group out of the boxes (ELEC-EQU-17, ELEC-MED-12).
- **Verify:** no circuit `under_repair` without a technician; no `verified` without insulation, PE and RCD trip
  measured; each energizing has who and when in the note.
- **Don't:** mark `verified` "because it works"; delete bad measurements (ELEC-MED-16); let a technician switch on their
  circuit because it shows `repaired`.
- **Source:** `survey.json` contract; ELEC-MED-1 to 6, ELEC-MED-12, ELEC-MED-16; ELEC-EQU-11, ELEC-EQU-17,
  ELEC-EQU-27; Decreto 911/96 art. 79 c) (insulation test before re-energizing, per ELEC-EQU-17) and d).

### ELEC-PLA-21: Know what the drawing is worth: approximate, unsigned, for working
- **Rule:** the generated drawing is a survey sketch: approximate scale, schematic routes, data only as
  good as what was surveyed. The title block says so ("Approximate sketch, not to scale"; "Croquis orientativo, no a escala" on a Spanish drawing, when `source` indicates it).
- **Why:** nobody should chase a wall trusting that the conduit runs "where the line is", or present it as a
  design or an as-built drawing.
- **How:** before cutting or drilling, a cable detector and the criterion of ELEC-SEG-19; to submit, a signed design
  (ELEC-PLA-3); when finished, an as-built drawing (ELEC-PLA-22).
- **Verify:** the title block shows date, source and "not to scale" where applicable.
- **Don't:** take measurements off the PDF with a ruler; delete the "not to scale" legend so it "looks neater".
- **Source:** this guide's criterion; AEA 770:2017, 770.2.1 (design signed by a professional with the relevant competence).
## Several technicians on the same drawing

### ELEC-PLA-24: Teamwork goes in phases, and the phase decides what gets locked out
- **Rule:** in a house with leakage and short circuits, the work of several technicians follows four phases in order, and nobody moves to
  the next one until the person in charge (*responsable*) says so:
  1. **Live mapping** (ELEC-PLA-11, 13): exclusive phase; nobody opens boxes or the panel (distribution board, *tablero*).
  2. **Dead diagnosis** (ELEC-PLA-11 step 5, ELEC-EQU-2, ELEC-EQU-5): the whole team under the **group lockout
     of the main switch**, with a group lockbox and one personal padlock per technician (ELEC-EQU-20). Essential service runs
     on a protected temporary supply (*provisorio*) (ELEC-EQU-9). Circuits are identified, insulation-tested (*megar*) circuit by circuit in coordinated windows (ELEC-EQU-27)
     and the neutral matrix is built.
  3. **Sectioning** (ELEC-EQU-7): the panel is rebuilt or rearranged with several 30 mA RCDs (*disyuntor* / *diferencial*, ID), double-pole PIAs and neutrals
     separated per circuit, leaving no circuits outside the RCD.
  4. **Independent packages** (ELEC-EQU-8): only once the panel is sectioned, the neutrals checked and there are no boxes
     shared between packages, each technician locks out the double-pole PIA of their package and works with their sheet (ELEC-PLA-19).
     Within the circuit, the fault is found by halving (ELEC-DIA-2).
- **Why:** with one PIA locked out, a neutral shared or crossed with a colleague's circuit still carries
  current and voltage to earth (ELEC-EQU-24). Until that has been ruled out, the only disconnection that protects everyone
  is the main switch.
- **How:**
  - The person in charge (ELEC-EQU-12) keeps the **lockout log**: which device is locked out, whose padlocks
    are in the group lockbox, which sources were locked out (ELEC-EQU-26). The `survey.json` contract has no fields
    for that: it goes in the work permit and on the tag of the group lockbox (ELEC-EQU-20), and a summary in `notes` of
    each circuit ("lockout: CG, group lockbox; padlocks A, B, C"), so it appears on the sheet and in the JSON the
    agent reads.
  - Each technician's sheet carries, written by the person in charge if the tool does not print it, the current phase and what
    is locked out (ELEC-PLA-19).
  - **Occupied house:** the occupants know what works, that the panel is not to be touched and who their contact is; the panel
    is signposted and, if possible, locked (ELEC-EQU-28).
  - **End of the workday and change of technician:** nothing half-done is left energized; whatever is incomplete stays under the person in charge's
    operations padlock and tag (ELEC-EQU-18). The incoming person puts on their padlock before the outgoing person removes
    theirs, and they hand over the sheet in person; `assigned_to` is updated with `plan status` (ELEC-EQU-19). If someone left with
    their key, ELEC-EQU-22.
- **Verify:** at every moment, each technician can say which phase the job is in and which device protects them; the day's `plan
  summary` matches the panel and the lockout log.
- **Don't:** hand out per-circuit sheets with PIA lockout while there are single-pole devices, unchecked neutrals or circuits
  outside the RCD; mix mapping with work in progress; move to the next phase "because it's almost there".
- **Source:** ELEC-EQU-5, 7, 8, 9, 12, 18 to 20, 22, 24, 26 to 28 ([teamwork-and-rehabilitation.md](teamwork-and-rehabilitation.md));
  Decreto 911/96 art. 79 a) II (lockout of isolating devices with a label and the name of the person in charge). The order
  in four phases is this guide's criterion, consistent with ELEC-EQU-24; **not verified in a primary source** as a
  standardized procedure.

### ELEC-PLA-25: A box with cables from several circuits is drawn in all its routes
- **Rule:** in the contract, each point has **only one** `circuit`. A junction or branch box through which
  conductors of several circuits pass is entered as `junction_box` with `circuit` set to one of them and a `note` that lists
  all of them ("TUG2, IUG1 pass through"), and its id is included in the `sequence` of **each** route that goes through it. That way `validate`
  warns `mixed_run` (mixed route) on the other circuits (ELEC-PLA-18). If the box has no `circuit`, that warning does not appear.
- **Why:** it is the only way for the drawing to show the shared box. That way the agent detects that two circuits
  assigned to different technicians share a box (ELEC-EQU-8): those circuits go into a single package or are separated first.
- **How:** when surveying or when opening a box under lockout/tagout (LOTO, *consignación*), write down which circuits pass through. With the mixed-route
  warnings (or by looking for ids that appear in more than one `sequence`), the agent sees which circuits share a box and, if the
  assignees are different, flags it before generating sheets (ELEC-PLA-18). On the drawing and in the DXF, check the box's `note`:
  the symbol alone does not say which circuits pass through.
- **Verify:** no box appears in routes of circuits assigned to different people while there is work in
  progress on both.
- **Don't:** enter the box twice with different ids to "split it"; assume that a junction box carries a single
  circuit because the old drawing showed it that way.
- **Source:** `survey.json` contract (one circuit per point; routes with a sequence of ids); mixed-route
  warning of `validate` (`electricidad_plan.py`); ELEC-EQU-8;
  770.6.6 note 1 (junction and branch boxes with more than one circuit).

## As-built drawing

### ELEC-PLA-22: When finished, the as-built drawing shows what was left, not what was planned
- **Rule:** once the work is finished, an as-built drawing (*conforme a obra*) is delivered with what was **actually** left:
  panels and their location, each outlet point (*boca*) with its circuit, real conduit routes with dimensions and wiring, junction boxes,
  earth electrode and its conduit, and the updated single-line diagrams of each panel, with date and version.
- **Why:** the next person who works on it, the owners' association (*consorcio*) or the ART (workers' compensation insurer) need to know what is there; a design drawing that does not
  match what was built is worse than having no drawing.
- **How:** start from the updated `survey.json` (all circuits `verified`), correct routes with the
  photos of the wall chases before plastering (ELEC-CON, see
  [conductors-and-conduits.md](conductors-and-conduits.md)), export `plan dxf` and finish the dimensioned drawing
  in CAD. Reference content: that of Anexo 770-A.1.2 and 770-A.1.3 applied to what was built, plus test reports
  (ELEC-MED-11). A copy of the single-line diagram goes on the panel door (ELEC-TAB-18).
- **Verify:** each circuit of the panel is on the drawing and in the single-line diagram; each outlet point on the drawing exists on site.
- **Don't:** deliver the design drawing as as-built; deliver the "not to scale" sketch as an as-built
  drawing.
- **Source:** AEA 770:2017, Anexo 770-A, note (as-built documentation is not in the annex and may be required
  as determined by the enforcement authority) and 770-A.1.2/A.1.3 (content of single-line diagram and drawing); AEA 90364-7-772:2019, 772.4.4
  (as-built documentation, for buildings; seen in the table of contents, see ELEC-EDI-25); ELEC-MED-11.

### ELEC-PLA-23: The as-built is signed by whoever has the professional competence (*incumbencia*), and is filed with the job folder
- **Rule:** when the jurisdiction, the utility (distribution company, *distribuidora*) or the client (*comitente*) asks for an as-built, the drawing and the single-line diagrams are
  signed by the professional or qualified electrician (*instalador habilitado*) with competence in that jurisdiction and for that category of work; they are
  filed with the job folder (paper and PDF, plus the DXF).
- **Why:** the signature takes responsibility that what is drawn is what was built; the utility, the municipality or
  the ART can ask for it.
- **How:** confirm the signer's license (*matrícula*) and scope (ELEC-NOR-8, ELEC-NOR-12); keep with the folder: drawing,
  single-line diagrams, load schedule, test reports, DCI (installation conformity declaration) or certificate if applicable (ELEC-MED-11).
- **Verify:** signature, license, date and version in the title block; the version matches the one on the panel.
- **Don't:** sign for someone else or "lend" the signature (ELEC-NOR-16); let the agent or the tool appear as
  authors.
- **Source:** the 770:2017 does not regulate the as-built (note to Anexo 770-A: it may be required as determined by the
  enforcement authority); 770.2.1 governs only the design. Who signs: ELEC-NOR-8, ELEC-NOR-12, ELEC-NOR-16 and the
  local authority. **Not verified in a primary source:** that the signature of the as-built belongs to the professional with
  competence as a general rule (inferred from the approval rules of each jurisdiction) and the requirements of each
  municipality or professional council (*colegio*).

## Worked example: house with MCBs tripped by leakage

Situation: single-storey house, main panel in the hallway with a main switch, two RCDs and six MCBs (*térmicas*); three
MCBs are off because they kept tripping (leakage and short circuits). There are no drawings. The house is occupied. Three technicians and a
person in charge are working. "Arreglar desde el fondo" (fix it from the bottom up) is taken as a full repair (see
[teamwork-and-rehabilitation.md](teamwork-and-rehabilitation.md)). If it also means the back of the
house (yard, garden, outdoor areas), it matches the risk-based priority: outdoor areas and wet locations are the usual
suspects and go first (ELEC-EQU-4, ELEC-EQU-6).

1. **Survey (ELEC-PLA-6 to 10).** Walkthrough, sketch by eye with paced measurements of five rooms, 23 outlet points numbered and
   photographed; photo of the panel without removing the inner cover (dead front, *contratapa*); list of sources (there is no generator set, UPS or solar panels).
2. **Live mapping (ELEC-PLA-11, 13).** Exclusive phase, in pairs with handheld radios (*handy*), occupants notified: the circuits that
   **hold** (C1, C2, C4) are mapped. The three that were off **are not switched on**: their outlet points stay `unverified`.
3. **The agent builds the JSON (ELEC-PLA-17)** and runs `validate`. Errors: TUG3 with no 30 mA RCD upstream (it was
   hanging from the main switch, ELEC-PRO-7) and socket outlet p4 in the bathroom (wet) with no RCD (ELEC-PRO-7, ELEC-ESP-4). Warnings: TUG3 cross-section not
   entered, so the 20 A C5 cannot be checked (ELEC-REV-11), and 1.5 mm² PE on IUG1 (minimum 2.5, ELEC-CON-6). With
   errors, no per-circuit sheets are handed out: those errors are resolved in the sectioning (step 5). In the agent's
   review (ELEC-PLA-18), TUG3 has `unverified` points and an unchecked neutral: until the diagnosis is finished the
   main switch is locked out.
4. **Diagnosis under group lockout (ELEC-PLA-24 phase 2).** First, the person in charge sets up a temporary panel with a PIA, a 30 mA
   RCD and earthed socket outlets for the fridge and some lighting (ELEC-EQU-9). Then they lock out the main switch with an
   operations padlock, keys in the group lockbox and one personal padlock per technician (ELEC-EQU-20). With the house locked out, circuits are
   identified by continuity, with conductors disconnected (ELEC-PLA-11 step 5), insulation-tested circuit by circuit in
   announced windows (ELEC-DIA-4, ELEC-EQU-27) and the neutral matrix is built (ELEC-EQU-5). Result: TUG3 with insulation
   of 0.2 MΩ; IUG2 with a short circuit in a bathroom wall light; the neutral of TUG2 is crossed with that of IUG1 in a junction box
   in the hallway (entered as in ELEC-PLA-25).
5. **Sectioning (ELEC-PLA-24 phase 3, ELEC-EQU-7).** The person in charge rearranges the panel: TUG3 moves to its own 30 mA
   RCD, the neutrals of TUG2 and IUG1 are separated and the MCBs become double-pole. Everything stays under the group lockout.
6. **Packages and sheets (ELEC-PLA-24 phase 4, ELEC-PLA-19).** No boxes shared between packages: Technician A, TUG3
   (kitchen, bathroom and laundry); Technician B, IUG2 (bathroom). TUG2 and IUG1 shared a box, so they go together into a single package:
   Technician C. Each one locks out the double-pole PIA of their package with a DIN lockout device and their padlock, verifies at each box and finds the
   fault by halving (ELEC-DIA-2). If any package does not meet the conditions, it stays under the main switch.
7. **Close-out and progress (ELEC-PLA-20, ELEC-EQU-11, ELEC-EQU-17).** Each repaired circuit is measured and set to `repaired`; the
   person in charge energizes it, with notice and the people counted, and records who energized; with insulation, PE and RCD trip
   entered it moves to `verified`. `plan status` at each change; `plan summary` and end-of-day walkthrough (ELEC-EQU-18).

Excerpt of the `survey.json` the agent builds (abridged):

```json
{
  "version": 1, "job": "back-house", "source": "by-eye sketch", "date": "2026-11-15",
  "supply": {"type": "single_phase", "voltage_v": 220},
  "floors": [{"id": "PB", "name": "Ground floor"}],
  "rooms": [
    {"id": "coc", "name": "Kitchen", "floor": "PB", "polygon": [[0,0],[3.5,0],[3.5,3],[0,3]], "wet": false},
    {"id": "ban", "name": "Bathroom", "floor": "PB", "polygon": [[3.5,0],[5.5,0],[5.5,2],[3.5,2]], "wet": true}
  ],
  "panels": [{"id": "TP", "name": "Main panel", "floor": "PB", "x": 3.6, "y": 2.8, "upstream": null}],
  "devices": [
    {"id": "CG", "panel": "TP", "type": "MCB", "poles": 2, "in_a": 40, "curve": "C", "icn_ka": 4.5, "upstream": null, "label": "GENERAL"},
    {"id": "ID1", "panel": "TP", "type": "RCD", "poles": 2, "in_a": 40, "idn_ma": 30, "class": "AC", "upstream": "CG"},
    {"id": "C1", "panel": "TP", "type": "MCB", "poles": 2, "in_a": 10, "curve": "C", "upstream": "ID1", "label": "LIGHTS"},
    {"id": "C5", "panel": "TP", "type": "MCB", "poles": 2, "in_a": 20, "curve": "C", "upstream": "CG", "label": "KITCHEN"}
  ],
  "circuits": [
    {"id": "IUG1", "type": "IUG", "name": "Kitchen and bathroom lights", "device": "C1", "section_mm2": 1.5, "pe_mm2": 1.5,
     "status": "surveyed", "assigned_to": "", "notes": "", "measurements": []},
    {"id": "TUG3", "type": "TUG", "name": "Kitchen, bathroom and laundry sockets", "device": "C5", "section_mm2": null, "pe_mm2": null,
     "status": "fault", "assigned_to": "Technician A", "notes": "MCB tripped, not switched back on; neutral not checked: lock out CG (diagnosis)",
     "measurements": [{"date": "2026-11-15", "type": "insulation", "value": 0.2, "unit": "MOhm", "ok": false}]}
  ],
  "points": [
    {"id": "p1", "type": "ceiling_light", "floor": "PB", "room": "coc", "x": 1.75, "y": 1.5, "height_m": null, "circuit": "IUG1", "status": "ok", "letter": "a", "note": ""},
    {"id": "p2", "type": "switch", "floor": "PB", "room": "coc", "x": 3.3, "y": 2.6, "height_m": 1.15, "circuit": "IUG1", "status": "ok", "letter": "a", "note": ""},
    {"id": "p3", "type": "socket", "floor": "PB", "room": "coc", "x": 1.0, "y": 0.1, "height_m": 1.1, "circuit": "TUG3", "status": "unverified", "note": "countertop"},
    {"id": "p4", "type": "socket", "floor": "PB", "room": "ban", "x": 4.0, "y": 1.9, "height_m": 1.2, "circuit": "TUG3", "status": "unverified", "note": "next to the washbasin"}
  ],
  "runs": [{"circuit": "IUG1", "sequence": ["TP", "p2", "p1"]}]
}
```

Commands:

```bash
gateway electricidad plan validate /workdir/electricidad/back-house/survey.json
gateway electricidad plan draw /workdir/electricidad/back-house/survey.json --color status --format pdf
gateway electricidad plan single-line /workdir/electricidad/back-house/survey.json
gateway electricidad plan sheets /workdir/electricidad/back-house/survey.json --tech "Technician A"
gateway electricidad plan status /workdir/electricidad/back-house/survey.json TUG3 under_repair --tech "Technician A" --note "low insulation, check box p3"
gateway electricidad plan summary /workdir/electricidad/back-house/survey.json
```

In this example, `validate` gives two errors and two warnings. Errors: TUG3 with no 30 mA RCD upstream (ELEC-PRO-7) and socket outlet
p4 in the bathroom (wet room) with no RCD (ELEC-PRO-7, ELEC-ESP-4). Warnings: TUG3 cross-section not entered, which prevents checking the 20 A
C5 (ELEC-REV-11), and 1.5 mm² PE on IUG1 (ELEC-CON-6). The agent's review (ELEC-PLA-18) adds that TUG3 has
`unverified` points and an unchecked neutral. Since its `notes` mentions the neutral, the printed sheet adds the lockout
of the main switch. These are exactly the issues to resolve. Technician A's sheet is generated only after sectioning and
entering the new RCD, when `validate` comes out with no errors.

## What this guide does not replace
- A survey sketch **guides** the work; it is not a design, nor an as-built drawing, nor a certificate.
  The design, the DCI or certificate and the as-built are signed by a professional or qualified electrician with
  competence in the jurisdiction (see [regulations-and-permits.md](regulations-and-permits.md)).
- The current **IRAM 2010** and **IEC 60617** (paid) prevail over this guide's description of symbols; the
  **utility**, the **municipality** and the **professional council** decide which documentation and format they accept.
- The current AEA Reglamentación (770:2017 and Ed. 2026 when available, 771, 772) and the data sheets of the
  manufacturers of instruments and circuit finders.
- No map, sheet or status from the tool authorizes working without isolating (*consignar*), locking out and verifying absence of
  voltage on site (ELEC-SEG-3 to 5), or live work. A circuit showing `repaired` does not authorize
  anyone to energize it: the person in charge energizes it (ELEC-EQU-17).
- Team organization, the work permit and group lockout are in
  [teamwork-and-rehabilitation.md](teamwork-and-rehabilitation.md). This guide only carries them onto the drawing and
  the sheets.
