---
title: Survey and drawing examples (house with the panel from the photo; single-phase building, ground floor + 4 floors)
scope: the guide's example surveys (survey.json), the outputs generated with `gateway electricidad plan` (floor plans, single-line diagrams, work sheet, DXF), how to regenerate them, and a walk-through of the guide's example case (4-floor building with single-phase apartments and the three-phase panel from the photo) with the calculations done with the calculator
when_to_use: see what a complete survey.json looks like before building one; show someone what the tool delivers; regenerate the outputs after changing electricidad_plan.py; follow the guide's example case end to end, from the building to an apartment's panel and to the house in the photo
related: [../README.md, ../surveys-and-drawings.md, ../buildings.md, ../panels.md, ../reviewing-a-panel.md, ../teamwork-and-rehabilitation.md, ../grades-and-circuits.md, ../protection.md]
as_of: 2026-11-15
sources: [aibridge/electricidad guide (buildings.md "Example case", panels.md ELEC-TAB-18 and ELEC-TAB-26, reviewing-a-panel.md "Worked example"), calculator electricidad.py and electricidad_plan.py of 2026-11-15 (real outputs copied below)]
---
# Survey and drawing examples

Two example jobs, built with the `survey.json` contract from
[surveys-and-drawings.md](../surveys-and-drawings.md) ("The `survey.json` contract"). The floor plans are
**made up** to show the tool: they are not real jobs or projects that can be signed (ELEC-PLA-21). There are no new rules
here: everything applied is cited with its ID in the guide.

| File | What it is | Outputs |
|---|---|---|
| [house-panel-photo.json](house-panel-photo.json) | Single-story house with the **three-phase panel (*tablero*) from the photo** (`photo_2026-11-15_04-35-27.jpg`, not published): protective devices, labels and ratings read from the photo; the handwritten labels are copied as written, and whatever is unreadable appears as "illegible", "(no label)" or "(doubtful)". A single 4-pole RCD (*disyuntor* / *diferencial*, ID) for 27 circuits: that is why `validate` gives warnings (see below) | [output-house/](output-house/) |
| [building-4-floors.json](building-4-floors.json) | **Building, ground floor + 4 floors, 8 single-phase apartments (*deptos*)**: the case from [buildings.md](../buildings.md) ("Example case"). Meter cabinet with each apartment's main panel, common services (landings, emergency lighting, service socket outlets, garages, door entry system, gate, pumps, elevator), each floor's landing, and **apartment 4A** (the farthest one) complete, with its sub-panel (*tablero seccional*). For the other seven apartments only the panel and its sub-panel appear | [output-building/](output-building/) |

## How to regenerate the outputs

The tool only writes inside the job folder (`--out` relative to it), so first copy each example as the `survey.json` of
a job in `/workdir/electricidad/` (or in the folder set by the `ELECTRICIDAD_DIR` variable). That way the sheets cite the
job by its name and no machine path is left in the files. The published renders are in English (`--lang en`) and only SVG, MD and DXF (`--format svg`): PNG and PDF
are what the tool sends in a chat, they are not kept in the repo (the default `--format png` writes the PNG next to the SVG); without
`--lang`, drawings and sheets come out in the language of the prefs file, else Spanish.

```bash
EX=/usr/local/share/aibridge/electricidad/examples
for j in house-panel-photo building-4-floors; do
  mkdir -p /workdir/electricidad/$j && cp $EX/$j.json /workdir/electricidad/$j/survey.json
done
L="--lang en --format svg"

# house with the panel from the photo (outputs in house-panel-photo/output/)
J=house-panel-photo
gateway electricidad plan validate    $J
gateway electricidad plan draw        $J $L
gateway electricidad plan draw        $J --color status $L
gateway electricidad plan draw        $J --only IUG9 $L
gateway electricidad plan single-line $J $L
gateway electricidad plan sheets      $J --circuit ACU1 $L
gateway electricidad plan dxf         $J $L

# building, ground floor + 4 floors (outputs in building-4-floors/output/)
J=building-4-floors
gateway electricidad plan validate    $J
gateway electricidad plan draw        $J --floor PB $L
gateway electricidad plan draw        $J --floor P1 $L
gateway electricidad plan draw        $J --floor P4 $L
gateway electricidad plan draw        $J --floor P4 --color status $L
gateway electricidad plan single-line $J --panel TP-SG,TS-BOM,TS-ASC $L
gateway electricidad plan single-line $J --panel GM,TS-4A $L
gateway electricidad plan sheets      $J --circuit TUG2 $L
gateway electricidad plan dxf         $J --floor P4 $L
```

Then copy each job's `output/` into this folder: the house's as `output-house/`, the building's as `output-building/`.
Before copying them, search the SVG, MD and DXF files for machine paths (`grep -l -E '/(home|tmp)/' ...` must find
nothing). What you get:

| Folder | Files |
|---|---|
| [output-house/](output-house/) | `plan_PB_circuit`, `plan_PB_status`, `plan_PB_circuit_only-IUG9`, `single-line`, `sheet_ACU1` (`.svg`, the sheet also `.md`), `survey_PB.dxf` |
| [output-building/](output-building/) | `plan_PB_circuit`, `plan_P1_circuit`, `plan_P4_circuit`, `plan_P4_status`, `single-line_TP-SG-TS-BOM-TS-ASC`, `single-line_GM-TS-4A`, `sheet_TUG2` (`.svg`, the sheet also `.md`), `survey_P4.dxf` |

**What `validate` gives:**

- `building-4-floors`: **0 errors, 0 warnings.** What `validate` does not check, the agent did by hand (second table of
  ELEC-PLA-18): TUG2 is `under_repair` with socket outlet a29 in `fault`; the `verified` circuits have insulation,
  PE continuity and RCD trip test entered.
- `house-panel-photo`: 0 errors, 18 warnings, all on purpose: MCBs (*térmicas*) and cross-sections unreadable in the photo
  (ELEC-REV-5, ELEC-REV-11), outlet points (*bocas*) whose circuit was not identified (ELEC-PLA-5), the RCD class that
  cannot be read (ELEC-PRO-9), the single RCD that protects too many circuits (ELEC-REV-10) and an outdoor socket outlet
  on a TUG (ELEC-CIR-11). These are the data you
  have to go out and survey.

## Case walk-through: single-phase 4-floor building + the panel from the photo

The calculations are real outputs of the calculator (`gateway electricidad ...`, which is `electricidad.py`), trimmed to
the lines that matter. The values are illustrative: in a real project they come from the current standard and are signed
by a qualified professional.

### 1. The building: demand, phases and feasibility

[buildings.md](../buildings.md), "Example case: ground floor + 4 floors, 8 single-phase apartments": 8 apartments of 7 kVA
with a diversity (simultaneity) factor of 0.8 plus 8.5 kVA of common services = 53.3 kVA. Phase allocation (ELEC-EDI-10):
L1 = 1A, 2B, 4A; L2 = 1B, 3A, 4B; L3 = 2A, 3B and the single-phase services. In the JSON, the allocation goes in the label
of each `Q0-..` and in the name of each `TS-..`.

```text
$ gateway electricidad current --power 53300 --va --system three
I = S / (√3 × U) = 53300 VA / (√3 × 380 V) = 80.98 A
$ gateway electricidad current --power 19100 --va --system single      # most loaded phase (L1)
I = S / (U) = 19100 VA / (220 V) = 86.82 A
```

For the utility (distribution company), the most loaded phase governs (≈ 87 A), not the average (≈ 81 A). 53 kVA is close
to the 60 kVA of ELEC-EDI-2: request the feasibility study with the calculation done (ELEC-EDI-1).

### 2. The line to each apartment (sub-main up the riser)

Each apartment's main panel is in the meter cabinet, ≤ 2 m from the meter (ELEC-EDI-6); one sub-main (feeder) circuit runs
up the riser (*montante*), each in its own conduit (ELEC-EDI-7), with 1% voltage drop at most because the apartment follows
771 (ELEC-EDI-8, ELEC-EDI-26).

```text
$ gateway electricidad drop --current 31,6 --length 20 --section 16 --line submain
ΔU = 2 × 31.6 A × 0.02 km × (1.4477 × 0.85 + 0 × 0.53) = 1.56 V → 0.71 % of 220 V
✅ drop_submain [770.15.6 note (recommendation) / 771.13 b) note (requirement)]: 0.71 % (max. 1 %, partial, of the sub-main circuit)
$ gateway electricidad drop --current 31,6 --length 20 --section 10 --line submain
❌ drop_submain [770.15.6 note (recommendation) / 771.13 b) note (requirement)]: 1.12 % (max. 1 %, partial, of the sub-main circuit); mandatory in the 771, a recommendation in the 770
```

With `gateway electricidad size --current 31,6 --length L --circuit submain`, floor by floor (this is how it ended up
in the name of each `TS-..` in the JSON):

| Floor | Approx. length | Proposed cross-section | Voltage drop | What governs |
|---|---|---|---|---|
| 1st | 8 m | 6 mm² | 0.77% | current-carrying capacity (Iz 36 A ≥ MCB 32 A) |
| 2nd | 12 m | 10 mm² | 0.67% | voltage drop |
| 3rd | 16 m | 10 mm² | 0.89% | voltage drop |
| 4th | 20 m | **16 mm²** | 0.71% | voltage drop |

Many jobs make all of them 16 mm² to keep it simple (buildings.md, example case). The drawing does not show these lines:
see "What the drawing does not show well yet" at the end.

### 3. Each apartment's main panel, in the meter cabinet

[panels.md](../panels.md), ELEC-TAB-18: `Q0` MCB (PIA) 2×32 A C curve (protects the sub-main) + `ID0` 2×40 A 300 mA
selective "S" (indirect contact on the sub-main; ELEC-EDI-12, ELEC-PRO-12). Single-line diagram (*unifilar*):
[single-line_GM-TS-4A.svg](output-building/single-line_GM-TS-4A.svg).

```text
$ gateway electricidad earth --ra 40 --idn 300
Ra × IΔn = 40 Ω × 0.3 A = 12 V (limit UL 24 V)
⚠️ idn [770.14.2.3 / 771.18.3.5]: IΔn 300 mA gives no additional protection against direct contact: final circuits take an RCD ≤ 30 mA
✅ ra_x_idn [770.14.3.2 / 771.3]: 12 V ≤ 24 V
```

The warning is exactly the reason for the 30 mA RCDs in the apartment's panel.

### 4. Inside apartment 4A: grade, circuits and sub-panel

Floor area of the rooms in the JSON ≈ 76 m² covered + 6 m² of semi-covered balcony. Outlet points per ELEC-CIR-7 (living
room 2 IUG + 4 TUG, bedrooms 1 + 3, kitchen 2 + 3 double socket outlets, laundry 1 + 2, bathroom 1 + 1, hall 1 + 1,
balcony 1, air conditioner on a TUE).

```text
$ gateway electricidad demand --area 76 --semi-covered 6 --iug 5 --iug 5 --tug 11 --tug 6 --tue 1 --norm 771 --system single
Calculation area = 76 + 50 % × 6 = 79 m² → grade by area: Medium
Sum = 8690 VA; the DPMS exceeds the cap of grade Medium and it becomes High
DPMS = 8690 VA × 0.8 (coef. grade High) = 6952 VA → 31.6 A
✅ min_circuits [771.8.2.2 / table 771.8.II]: meets the minimum number of circuits of grade High
$ gateway electricidad demand --area 76 --semi-covered 6 --iug 10 --tug 11 --tug 6 --tue 1 --norm 771 --system single
❌ min_circuits [771.8.2.2 / table 771.8.II]: missing 1 general-use lighting circuit(s) (IUG) (has 1, the grade asks for 2)
```

The case's 7 kVA per apartment comes from here (6952 VA, 31.6 A). **Difference from ELEC-TAB-18:** its example builds the
apartment with 1 IUG + 2 TUG + 1 TUE and calls it Medium grade; with the air conditioner's TUE the sum goes over the
Medium cap, the unit becomes High (ELEC-CIR-3) and High requires 2 IUG (ELEC-CIR-4). That is why 4A has **IUG1 and IUG2**.

Sub-panel `TS-4A` (Class II, in the unit's hall), in the form of ELEC-TAB-19:

```text
Q1   switch-disconnector 2×40 A (incoming) + voltage protector (ELEC-EDI-11)
├─ ID1 2×40 A 30 mA type A ── C1 2×10 IUG1 (living, balcony, bedrooms) | C2 2×16 TUG2 (kitchen, laundry, bathroom)
├─ ID2 2×40 A 30 mA type A ── C3 2×16 TUG1 (living, hall, bedrooms)    | C4 2×10 IUG2 (kitchen, laundry, bathroom, hall)
└─ ID3 2×25 A 30 mA type A ── C5 2×20 TUE1 (inverter air conditioner, own conduit)
```

Lights and socket outlets of the same area are on different RCDs: if a leakage in the kitchen socket outlets trips ID1,
the kitchen lights (IUG2, on ID2) stay on. It is the same criterion as the "single-phase equivalent" in
[reviewing-a-panel.md](../reviewing-a-panel.md). Sum per RCD: 26, 26 and 20 A (ELEC-TAB-10).

```text
$ gateway electricidad coordinate --ib 13 --in 20 --section 2,5                # TUE1 in its own conduit
✅ in_le_iz [770.15.2.1]: In 20 A ≤ Iz 21 A
$ gateway electricidad coordinate --ib 13 --in 20 --section 2,5 --grouped 2    # if it shared a conduit
❌ in_le_iz [770.15.2.1]: In 20 A > Iz 16.8 A: the cable can overheat without the protection tripping; lower the In or raise the section
$ gateway electricidad drop --current 16 --length 14 --section 2,5 --line final --upstream-drop 0,71
✅ drop_final [770.15.6 1. / 771.13 b) 1.]: 1.65 % in this run + 0.71 % upstream = 2.36 % (max. 3 %, total up to the point of use (lighting and sockets))
```

Floor plan: [plan_P4_circuit.svg](output-building/plan_P4_circuit.svg); progress by status:
[plan_P4_status.svg](output-building/plan_P4_status.svg); DXF for CAD:
[survey_P4.dxf](output-building/survey_P4.dxf) (one layer per circuit, ELEC-PLA-2).

### 5. Common services

`TP-SG` with its own three-phase meter and one sub-main per system (ELEC-EDI-12). Single-line diagram:
[single-line_TP-SG-TS-BOM-TS-ASC.svg](output-building/single-line_TP-SG-TS-BOM-TS-ASC.svg); ground floor:
[plan_PB_circuit.svg](output-building/plan_PB_circuit.svg).

- Elevator: `Q-ASC` 4P C16 + `ID-ASC0` 4P 300 mA S (type according to the drive, to be confirmed with the manufacturer) up
  to `TS-ASC` next to the shaft on the 4th floor: a lockable motive power isolation separate from the shaft light and the
  service socket outlet, which stay on with the power isolation open (ELEC-EDI-13).
- Pumps: `TS-BOM` with a 30 mA RCD and one motor protection circuit breaker (*guardamotor*) per pump; level control and
  alternation are not drawn (ELEC-EDI-14).
- Landings and stairs on two circuits with a stair light timer (ELEC-EDI-15); emergency lighting on the same RCD, so the
  self-contained units turn on if that RCD trips (ELEC-EDI-16); service socket outlets, garages and door entry system on
  another RCD; gate on its own RCD (ELEC-EDI-17, ELEC-TAB-19). The runs go up through the riser junction box on each floor
  ([plan_P1_circuit.svg](output-building/plan_P1_circuit.svg)).

### 6. Progress and work sheet

The JSON shows progress halfway through the job: almost everything `verified` or `surveyed`, IUG2 and the gate `measured`,
the emergency lighting `surveyed` (the autonomy test is missing) and **TUG2 `under_repair`** assigned to "Technician B" for an insulation resistance of 0.4 MΩ at the washing machine box. Its sheet:
[sheet_TUG2.md](output-building/sheet_TUG2.md) ([SVG](output-building/sheet_TUG2.svg)), per ELEC-PLA-19 and ELEC-PLA-20.
The sheet says to lock out C2 in `TS-4A` and, if the panel is opened, the "main switch" `Q0-4A`: that
device is in the meter cabinet on the **ground floor**, not in the apartment. This is correct, because the incoming
terminals of `Q1` stay live from the sub-main, but the person in charge has to write it on the sheet (ELEC-SEG-28,
ELEC-TAB-28).

### 7. The panel from the photo: three-phase, and its single-phase equivalent

The panel from the photo is **not** that of an apartment in this building: it is **three-phase** (3 × 380/220 V + N). You
can tell by the 4-pole devices: RCD 4P 63 A 30 mA, main 4P C40 and another 4P MCB, plus 26 two-pole 220 V MCBs
(ELEC-REV-4, ELEC-REV-7). Full reading: [reviewing-a-panel.md](../reviewing-a-panel.md), "Worked example: real panel
sent by photo".

```text
$ gateway electricidad current --current 40 --system three
S = √3 × U × I = √3 × 380 V × 40 A = 26327 VA
$ gateway electricidad current --current 40 --system single
S = U × I = 220 V × 40 A = 8800 VA
```

A 40 A incoming device lets through ≈ 26.3 kVA in three-phase and 8.8 kVA in single-phase. What can actually be used is
limited by the contracted power.

**Single-phase equivalent:** for an apartment like 4A, everything is 2-pole (incoming switch, RCD and MCB), with a single
phase color and no phase balancing inside the unit (the building does the balancing, ELEC-EDI-10). It is the `TS-4A`
above (with the `Q0` + `ID0` of the meter cabinet upstream), which matches "What the single-phase equivalent would look
like" in [reviewing-a-panel.md](../reviewing-a-panel.md) and ELEC-TAB-18. If a 4-pole RCD is reused in a single-phase
installation, connect the poles the manufacturer indicates (ELEC-REV-7); a 2P one is preferable.

**Taking it to the rules:** [panels.md](../panels.md), ELEC-TAB-26 ("The panel from the photo"). Inner cover (dead front,
*contratapa*) now; RCDs split into groups of 2 or 3 circuits, with pool, gate and outdoor circuits separate; busbar combs
(*peines*); one neutral terminal block per RCD; phases measured.

**Rehabilitating the house in the photo with a crew:**
[teamwork-and-rehabilitation.md](../teamwork-and-rehabilitation.md), "Case: the house whose panel grew in patches" (reading
the photo, plan by workdays for 3 people, group lockout ELEC-EQU-20, sectioning ELEC-EQU-7, independent work packages
ELEC-EQU-8). The starting survey is [house-panel-photo.json](house-panel-photo.json); its outputs are in
[output-house/](output-house/), including the sheet for the `ACU1` pump.

## What the drawing does not show well yet in a multi-story building

Observed when generating `output-building/` with `electricidad_plan.py` of 2026-11-15. It tells you what to complete by
hand:

- **Sub-main lines are not drawn.** A circuit that feeds a panel (`Q0-4A` → `TS-4A`) cannot be entered as a circuit
  without `validate` asking for a 30 mA RCD upstream (the sub-main has 300 mA S). That is why the riser appears empty and
  each `TS-..` stands alone on its floor. The cross-section and voltage drop are written in the panel's name.
- **Between floors there is no "comes from / goes up to".** The run is cut where it changes floor. In this example one
  junction box per floor was added in the riser so each section starts there. The light and socket outlet in the elevator
  pit (ground floor) appear without a line, because their panel is on the 4th floor.
- **The whole floor plan goes on one sheet.** Apartment 4A shares the sheet with the empty 4B, and its outlet points end up
  crowded (overlapping labels in laundry, bathroom and hall). There is no option to draw only one area.
- **The meter cabinet single-line diagram** stacks the 8 incoming devices in one column (a sheet almost 5000 px tall). The
  "S" for selective and the sub-main cross-section have no field of their own: they go in the label.
- **The status legend** of a floor plan counts the circuits of the whole building. "Circuits on this floor" includes one
  that only passes through the junction box.
- **The work sheet** names the "main switch" highest up the chain (`Q0-4A`) without saying which panel
  or which floor it is on.
- The 9 meters together are labeled correctly, but some labels end up closer to the neighboring meter. A floor's DXF
  declares layers for all circuits, even empty ones.
