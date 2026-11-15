#!/usr/bin/env python3
"""electricidad-plan: an electrical job's survey in one JSON file, and its drawings (guide aibridge/electricidad/, surveys-and-drawings.md).

  electricidad-plan new JOB [--dir DIR] [--lang es|ru|en] [--json]   create DIR/JOB/survey.json from the minimal template
  electricidad-plan validate F [--json]                       errors (ids, references, cable not protected, no 30 mA RCD...) and warnings, each with its rule
  electricidad-plan draw F [--floor PB] [--color circuit|status] [--only C1[,C2]] [--format svg|png|pdf] [--out DIR] [--lang es|ru|en] [--json]
  electricidad-plan single-line F [--panel TP] [--format svg|png|pdf] [--out DIR] [--lang es|ru|en] [--json]
  electricidad-plan sheets F [--tech NAME | --circuit C1[,C2]] [--format svg|png|pdf] [--out DIR] [--lang es|ru|en] [--json]
  electricidad-plan dxf F [--floor PB] [--out DIR] [--lang es|ru|en] [--json]   DXF R12 ASCII, layers ROOMS, DIMENSIONS, PANELS, TEXT and one per circuit
  electricidad-plan status F ID STATUS [--tech X] [--note TEXT] [--json]   circuit ID (or point ID); atomic write + .bak copy
  electricidad-plan summary F [--json]                        progress by circuit, technician and status
  electricidad-plan symbols [--lang es|ru|en] [--json]        the symbols it draws, with their name and source

F is the path to survey.json, or the job name (looks for $ELECTRICIDAD_DIR/JOB/survey.json; default /workdir/electricidad).
Coordinates in meters, origin at the bottom left of each floor; approximate values are fine ("by-eye sketch"). The person does not
write the JSON: the agent builds it from what they say, a photographed sketch or the photo of the panel (contract in surveys-and-drawings.md).
Outputs go next to the JSON, in output/; --out DIR must stay inside the job folder (a relative path is taken from it; ".." or a
symlink that leaves it is refused). `status` only rewrites a survey (version 1, .json, not a symlink), with an inter-process lock,
temp file + rename and a .bak copy. The SVG is always written; PNG and PDF are made with typst, rsvg-convert, ImageMagick
(magick/convert) or inkscape, the first one found; if there is none, it warns and the SVG stays. Default --format: png.
--lang picks the language of the text a person reads on drawings and sheets (es, ru or en); default: "lang" in $AIBRIDGE_PREFS
(/workdir/.prefs.json), else es. Tool output (stdout, --json) is always English.
Exit: 0 ok, 1 the survey has errors (validate), 2 invalid input or a file that cannot be read. No network.
Called as `gateway electricidad plan ...` or /usr/local/bin/electricidad-plan. The drawing is for guidance only: it does not replace
the design or the as-built drawing signed by a licensed professional (ELEC-PLA-21), and it never proves that a circuit is dead.
"""
import contextlib, datetime, json, math, os, re, shlex, shutil, subprocess, sys, tempfile, unicodedata
try:
    import fcntl
except ImportError:                                # outside Linux: no inter-process lock
    fcntl = None

AS_OF = "2026-11-15"
VERSION = 1
ROOT = os.environ.get("ELECTRICIDAD_DIR", "/workdir/electricidad")
PREFS = os.environ.get("AIBRIDGE_PREFS", "/workdir/.prefs.json")
LANGS = ("es", "ru", "en")
SURVEY = "survey.json"
OUT_DIR = "output"
STATUS_MARK = {"ok": "✅", "warn": "⚠️", "fail": "❌", "unknown": "❔"}
ORDER = {"fail": 0, "warn": 1, "unknown": 2, "ok": 3}
FONT = "DejaVu Sans, Liberation Sans, Arial, Helvetica, sans-serif"
WIDTH = 1600                                      # px: readable on a phone with zoom, and ~1600 px wide as PNG

DEVICE_TYPES = ("MCB", "RCD", "RCBO", "SWITCH", "FUSE", "SPD", "MPCB")
CIRCUIT_TYPES = ("IUG", "TUG", "IUE", "TUE", "ACU", "MBTF", "APM", "OTHER")
STATUSES = ("not_surveyed", "surveyed", "measured", "fault", "under_repair", "repaired", "verified")
POINT_STATUSES = ("ok", "fault", "doubtful", "unverified")
MEASUREMENT_TYPES = ("insulation", "pe_continuity", "rcd_trip", "voltage")
POINT_TYPES = ("ceiling_light", "wall_light", "switch", "double_switch", "two_way_switch", "socket", "double_socket", "socket_20a",
               "outdoor_socket", "junction_box", "ac", "water_heater", "pump", "motor", "door_phone", "doorbell", "tv", "data", "sensor",
               "emergency_light", "extractor_fan", "earth_rod", "meter")
SUPPLY_TYPES = ("single_phase", "three_phase")
# outlet points per ELEC-CIR-6 (AEA 771.7.6 note 1, 770.7.1): junction boxes and boxes holding only switches are not outlet points
NOT_OUTLET = ("switch", "double_switch", "two_way_switch", "junction_box", "earth_rod", "meter", "tv", "data")
NO_CIRCUIT_OK = ("earth_rod", "meter", "tv", "data", "door_phone", "junction_box")   # low-current and accessories: no circuit needed
SOCKETS = ("socket", "double_socket", "socket_20a", "outdoor_socket")
SWITCHES = ("switch", "double_switch", "two_way_switch")
THICK = ("TUE", "ACU", "APM")                     # motive power line: thick stroke (IRAM 2010, see surveys-and-drawings.md)
OUTSIDE_TOL = 0.3                                 # m: a point placed "by eye" may fall a little outside its room without being an error
SKETCH_WORDS = ("ojo", "croquis", "sketch", "by eye", "на глаз", "эскиз")          # words in `source` that mean "by-eye sketch"
UNDERGROUND_WORDS = ("subterr", "underground", "подзем")                           # words in a run's note that mean underground
NEUTRAL_WORDS = ("neutro", "neutral", "нейтрал")                                   # words in a circuit's notes or name about the neutral

# ---------------------------------------------------------------- tables (source on each one)
# Current-carrying capacity, IRAM NM 247-3 cables in conduit (method B1), 40 °C: AEA 90364-7-770 Ed. 2017, table 770.12.I
# (the same values electricidad.py uses, table "iz_b1"). (2 loaded conductors, 3 loaded conductors).
IZ_B1 = {1.0: (11, 10), 1.5: (15, 14), 2.5: (21, 18), 4.0: (28, 25), 6.0: (36, 32), 10.0: (50, 44), 16.0: (66, 59), 25.0: (88, 77),
         35.0: (109, 96), 50.0: (131, 117), 70.0: (167, 149), 95.0: (202, 180)}
IZ_SOURCE = "AEA 90364-7-770 Ed. 2017, table 770.12.I (B1, 40 °C)"
# Caps per circuit type: (max outlet points, outlet points from which it warns, max device rating [A], min cross-section [mm²]).
# AEA 90364-7-771 Ed. 2006, 771.7.6 and table 771.7.I; cross-sections: table 771.13.I and 770.11.I (summary in grades-and-circuits.md, ELEC-CIR-5).
# TUE: 12 outlet points in the 771, 15 in the 770 (single-family house): 13 to 15 is a warning, more than 15 an error. ACU: a single load.
CAPS = {"IUG": (15, None, 16, 1.5), "TUG": (15, None, 20, 2.5), "IUE": (12, None, 32, 2.5), "TUE": (15, 12, 32, 2.5),
        "APM": (15, None, 25, 2.5), "MBTF": (15, None, 20, 1.5), "ACU": (1, None, None, 2.5), "OTHER": (None, None, None, None)}
CAPS_SOURCE = "AEA 90364-7-771 Ed. 2006, table 771.7.I and 771.13.I; 770 Ed. 2017, table 770.6.I and 770.11.I"
PE_MIN = 2.5                                      # AEA 90364-7-770 Ed. 2017, 770.14.4.5 (ELEC-CON-6)

PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#332288", "#882255", "#117733", "#AA4499",
           "#44AA99", "#999933", "#661100", "#6699CC", "#4D4D4D"]   # Okabe-Ito + Paul Tol (colour-blind safe); no light yellow
STATUS_COLOR = {"not_surveyed": "#9E9E9E", "surveyed": "#6C8EBF", "measured": "#44AA99", "fault": "#C62828", "under_repair": "#E69F00",
                "repaired": "#0072B2", "verified": "#2E7D32"}

# ---------------------------------------------------------------- person-facing text (es / ru / en)
# Everything a person reads on a drawing, sheet, legend or DXF goes through this table. Spanish (rioplatense) is the source;
# the three languages carry the same content, safety text included. Data the person typed (room names, labels, notes) is never
# translated. Units and norm codes stay as they are.
TXT = {
    "es": {
        "footer": "Orientativo, armado desde el relevamiento: no reemplaza el plano firmado por un profesional habilitado (ELEC-PLA-21)",
        "st.not_surveyed": "sin relevar", "st.surveyed": "relevado", "st.measured": "medido", "st.fault": "FALLA",
        "st.under_repair": "EN REPARACIÓN", "st.repaired": "reparado", "st.verified": "verificado",
        "pst.ok": "ok", "pst.fault": "falla", "pst.doubtful": "dudosa", "pst.unverified": "sin verificar",
        "mt.insulation": "aislación", "mt.pe_continuity": "continuidad PE", "mt.rcd_trip": "disparo ID", "mt.voltage": "tensión",
        "dev.MCB": "PIA", "dev.RCD": "ID", "dev.RCBO": "ID+PIA", "dev.SWITCH": "INT", "dev.FUSE": "FUS", "dev.SPD": "DPS", "dev.MPCB": "GM",
        "rcd_class": "clase {c}",
        "job_unnamed": "obra sin nombre", "job": "obra",
        "tb.floor": "Piso: {f}", "tb.date": "Fecha del relevamiento: {d}", "tb.source": "Fuente: {s}", "tb.drawn": "Dibujado con electricidad-plan · {d}",
        "tb.sketch": "Croquis orientativo, no a escala", "tb.sketch2": "Medidas aproximadas (a ojo)", "tb.approx": "Medidas aproximadas",
        "plan.by_status": "{f} · color por estado", "plan.by_circuit": "{f} · color por circuito", "only": "solo {ids}",
        "wet": "húmedo", "north": "N", "no_circ": "s/c",
        "legend": "Referencias", "mark.fault": "boca con falla", "mark.doubtful": "boca dudosa",
        "runs_note": "Recorridos esquemáticos: unen las bocas en el orden relevado, no muestran por dónde va el caño. Trazo grueso: TUE, ACU, APM.",
        "line.under": "trazos: recorrido subterráneo (según la nota del recorrido)",
        "line.mbtf": "raya y punto: MBTF (señales, muy baja tensión)",
        "line.core": "línea con centro blanco: otro circuito con el mismo color (más de 15 circuitos)",
        "status_each": "Estado de cada circuito", "circ_sheet": "Circuitos de esta hoja", "circ_floor": "Circuitos en este piso",
        "sl.title": "Esquema unifilar: de arriba hacia abajo, red → cabecera → diferencial → térmicas → circuitos",
        "sl.section_unknown": "sección ?", "sl.to_panel": "→ tablero {p}", "sl.more": "+{n} circuitos más", "sl.no_circuit": "sin circuito cargado",
        "sl.also_feeds": "también alimenta: ", "sl.cycle": "{o}: referencia en ciclo", "panel": "tablero",
        "sl.fed_from": "Alimentado desde {u}", "sl.fed_in": " en el tablero {p}",
        "sl.utility": "Red de la distribuidora: {s} → medidor → línea principal → {t}",
        "sl.three": "trifásica 3×380/220 V", "sl.single": "monofásica 220 V",
        "sl.no_device": "Circuitos sin protección cargada: ",
        "sl.ex.MCB": "Térmica (PIA, interruptor automático)", "sl.ex.RCD": "Diferencial (ID) que secciona",
        "sl.ex.RCBO": "Diferencial con térmica (ID+PIA)", "sl.ex.SWITCH": "Interruptor-seccionador", "sl.ex.FUSE": "Fusible",
        "sl.ex.SPD": "Protector de sobretensión (DPS)", "sl.ex.MPCB": "Guardamotor",
        "sl.ticks": "Rayitas oblicuas sobre la línea = cantidad de polos. Cuadrito de color bajo cada circuito = estado:",
        "sl.symbols": "Símbolos: AEA 90364-7-771 Anexo 771-K (basados en IEC 60617). Armado desde el relevamiento: verificar en el tablero "
                      "antes de usarlo (el orden real de puentes y peines puede ser otro).",
        "sl.panels": "tableros {p}",
        "sh.pend.insulation": "Aislación con megóhmetro, sin tensión, cargas desconectadas (ELEC-MED-4, ELEC-EQU-2)",
        "sh.pend.pe": "Continuidad del PE hasta cada boca (ELEC-MED-3)",
        "sh.pend.rcd": "Disparo del ID con probador desde un toma de este circuito, al reponer (ELEC-MED-6)",
        "sh.no_label": "sin rótulo", "sh.lock": "{d} «{l}» ({t}) en {p} — {n}",
        "sh.no_device": "NO HAY PROTECCIÓN CARGADA: no se trabaja hasta identificarla (ELEC-PLA-11)",
        "sh.none_entered": "ninguna cargada", "sh.main": "general",
        "ck.1": "Cortar {d} y, si se abre el tablero o hay dudas, también el corte general ({g}); los bornes de entrada del general siguen "
                "con tensión (ELEC-SEG-3).",
        "ck.2": "Candado y tarjeta propios en la protección: un candado, una persona, una llave; si son varios, pasador múltiple "
                "(ELEC-SEG-4, ELEC-EQU-21).",
        "ck.3": "Probar el detector en una fuente con tensión, verificar ausencia de tensión EN CADA CAJA antes de abrirla (F-N, F-PE, N-PE{x}) "
                "y volver a probar el detector (ELEC-SEG-5, ELEC-EQU-25).",
        "ck.3x": ", y entre fases",
        "ck.4": "Cajas compartidas: cualquier cable de otro circuito se trata como vivo (ELEC-PLA-16).",
        "ck.5": "Avisar al equipo antes de usar el megóhmetro: también es una fuente de tensión (ELEC-EQU-27).",
        "ck.6": "Medir lo pendiente sin tensión y pasar el valor al agente (ELEC-MED-3, ELEC-MED-4, ELEC-PLA-20).",
        "ck.7": "Al terminar: cajas cerradas, herramientas afuera, retirar solo el candado propio y avisar; energiza el responsable "
                "(ELEC-SEG-7, ELEC-EQU-17).",
        "ck.neutral": "La térmica puede no cortar el neutro{x} o hay neutro dudoso: bloquear también el corte general (ELEC-EQU-24).",
        "ck.neutral_x": " (no se relevó si es bipolar)",
        "sh.unassigned": "sin asignar", "sh.name": "NOMBRE",
        "sh.title": "HOJA DE TRABAJO · {c} · {n} · asignado: {a}", "sh.lockout": "BLOQUEAR ANTES DE TOCAR NADA", "sh.upstream": "Aguas arriba: {u}",
        "sh.points": "Bocas de {c} ({n})", "sh.no_points": "sin bocas cargadas",
        "sh.heads": ["Boca", "Tipo", "Ambiente", "Altura", "Estado", "Nota"],
        "sh.ok": "OK", "sh.bad": "MAL",
        "sh.meas": "Mediciones cargadas", "sh.none_yet": "ninguna todavía", "sh.pending": "Mediciones pendientes", "sh.none": "ninguna",
        "sh.checklist": "Checklist de consignación (ELEC-PLA-19) — nunca trabajar con tensión",
        "sh.others": "Otros trabajando ahora en la obra (cada uno con su candado)", "sh.notes": "Notas del circuito",
        "sh.tell": "Al terminar, avisale al agente",
        "md.title": "# Hoja de trabajo — {c} · {n}", "md.info": "Obra: {j} · Estado: {s} · Asignado: {a} · Relevamiento del {d}",
        "md.img": "plano aislado de {c}", "md.lockout": "## Bloquear antes de tocar nada", "md.points": "## Bocas ({n})",
        "md.meas": "## Mediciones", "md.none_entered": "ninguna cargada", "md.pending": "Pendientes:",
        "md.checklist": "## Checklist de consignación (nunca trabajar con tensión)", "md.others": "## Otros trabajando ahora",
        "md.notes": "## Notas", "md.finish": "## Al terminar", "md.not_proof": "La hoja no prueba que el circuito esté sin tensión.",
        "dxf.approx": "aprox. {w} x {h} m", "dxf.approx1": "aprox. {w} m", "dxf.floor": "Piso: {f}", "dxf.date": "Fecha: {d}  Fuente: {s}",
        "dxf.sketch": "Croquis orientativo, no a escala", "dxf.meters": "Medidas aproximadas, en metros",
        "dxf.layers": "Una capa por circuito (CIRC_...): apagando capas queda la hoja de trabajo aislada",
        "sl.short": "Unifilar", "sh.short": "Hoja {c}",
        "ct.OTHER": "OTRO",
        "new.floor": "Planta baja", "new.panel": "Tablero principal",
    },
    "en": {
        "footer": "For guidance only, built from the survey: it does not replace the drawing signed by a licensed professional (ELEC-PLA-21)",
        "st.not_surveyed": "not surveyed", "st.surveyed": "surveyed", "st.measured": "measured", "st.fault": "FAULT",
        "st.under_repair": "UNDER REPAIR", "st.repaired": "repaired", "st.verified": "verified",
        "pst.ok": "ok", "pst.fault": "fault", "pst.doubtful": "doubtful", "pst.unverified": "unverified",
        "mt.insulation": "insulation", "mt.pe_continuity": "PE continuity", "mt.rcd_trip": "RCD trip", "mt.voltage": "voltage",
        "dev.MCB": "MCB", "dev.RCD": "RCD", "dev.RCBO": "RCBO", "dev.SWITCH": "SWITCH", "dev.FUSE": "FUSE", "dev.SPD": "SPD", "dev.MPCB": "MPCB",
        "rcd_class": "type {c}",
        "job_unnamed": "unnamed job", "job": "job",
        "tb.floor": "Floor: {f}", "tb.date": "Survey date: {d}", "tb.source": "Source: {s}", "tb.drawn": "Drawn with electricidad-plan · {d}",
        "tb.sketch": "Approximate sketch, not to scale", "tb.sketch2": "Approximate dimensions (by eye)", "tb.approx": "Approximate dimensions",
        "plan.by_status": "{f} · colored by status", "plan.by_circuit": "{f} · colored by circuit", "only": "only {ids}",
        "wet": "wet", "north": "N", "no_circ": "n/c",
        "legend": "Legend", "mark.fault": "faulty outlet point", "mark.doubtful": "doubtful outlet point",
        "runs_note": "Schematic runs: they join the outlet points in the surveyed order, they do not show where the conduit goes. "
                     "Thick line: TUE, ACU, APM.",
        "line.under": "dashes: underground run (from the run's note)",
        "line.mbtf": "dash-dot: MBTF (signals, extra-low voltage)",
        "line.core": "line with a white center: another circuit with the same color (more than 15 circuits)",
        "status_each": "Status of each circuit", "circ_sheet": "Circuits on this sheet", "circ_floor": "Circuits on this floor",
        "sl.title": "Single-line diagram: top to bottom, supply → main switch → RCD → MCBs → circuits",
        "sl.section_unknown": "section ?", "sl.to_panel": "→ panel {p}", "sl.more": "+{n} more circuits", "sl.no_circuit": "no circuit entered",
        "sl.also_feeds": "also feeds: ", "sl.cycle": "{o}: circular reference", "panel": "panel",
        "sl.fed_from": "Fed from {u}", "sl.fed_in": " in panel {p}",
        "sl.utility": "Utility supply: {s} → meter → main line → {t}",
        "sl.three": "three-phase 3×380/220 V", "sl.single": "single-phase 220 V",
        "sl.no_device": "Circuits with no protective device entered: ",
        "sl.ex.MCB": "MCB (miniature circuit breaker)", "sl.ex.RCD": "RCD (isolating)",
        "sl.ex.RCBO": "RCBO (RCD with MCB)", "sl.ex.SWITCH": "Switch-disconnector", "sl.ex.FUSE": "Fuse",
        "sl.ex.SPD": "Surge protective device (SPD)", "sl.ex.MPCB": "Motor protection circuit breaker",
        "sl.ticks": "Oblique ticks on the line = number of poles. Colored square under each circuit = status:",
        "sl.symbols": "Symbols: AEA 90364-7-771 Anexo 771-K (based on IEC 60617). Built from the survey: check it at the panel "
                      "before using it (the real order of jumpers and busbar combs may be different).",
        "sl.panels": "panels {p}",
        "sh.pend.insulation": "Insulation resistance with a megohmmeter, de-energized, loads disconnected (ELEC-MED-4, ELEC-EQU-2)",
        "sh.pend.pe": "PE continuity to every outlet point (ELEC-MED-3)",
        "sh.pend.rcd": "RCD trip with a tester from a socket outlet on this circuit, when re-energizing (ELEC-MED-6)",
        "sh.no_label": "no label", "sh.lock": "{d} \"{l}\" ({t}) in {p}: {n}",
        "sh.no_device": "NO PROTECTIVE DEVICE ENTERED: no work until it is identified (ELEC-PLA-11)",
        "sh.none_entered": "none entered", "sh.main": "main",
        "ck.1": "Switch off {d} and, if the panel is opened or there is any doubt, also the main switch ({g}); the incoming terminals of "
                "the main switch stay live (ELEC-SEG-3).",
        "ck.2": "Your own padlock and tag on the device: one padlock, one person, one key; if there are several of you, a lockout hasp "
                "(ELEC-SEG-4, ELEC-EQU-21).",
        "ck.3": "Prove the voltage tester on a live source, verify absence of voltage IN EVERY BOX before opening it (L-N, L-PE, N-PE{x}) "
                "and prove the tester again (ELEC-SEG-5, ELEC-EQU-25).",
        "ck.3x": ", and between phases",
        "ck.4": "Shared boxes: treat any cable of another circuit as live (ELEC-PLA-16).",
        "ck.5": "Warn the team before using the megohmmeter: it is also a voltage source (ELEC-EQU-27).",
        "ck.6": "Measure what is pending with the circuit dead and send the values to the agent (ELEC-MED-3, ELEC-MED-4, ELEC-PLA-20).",
        "ck.7": "When finished: boxes closed, tools out, remove only your own padlock and report; the person in charge re-energizes "
                "(ELEC-SEG-7, ELEC-EQU-17).",
        "ck.neutral": "The MCB may not break the neutral{x} or the neutral is doubtful: lock out the main switch too (ELEC-EQU-24).",
        "ck.neutral_x": " (whether it is double-pole was not surveyed)",
        "sh.unassigned": "unassigned", "sh.name": "NAME",
        "sh.title": "WORK SHEET · {c} · {n} · assigned to: {a}", "sh.lockout": "LOCK OUT BEFORE TOUCHING ANYTHING", "sh.upstream": "Upstream: {u}",
        "sh.points": "Outlet points of {c} ({n})", "sh.no_points": "no outlet points entered",
        "sh.heads": ["Point", "Type", "Room", "Height", "Status", "Note"],
        "sh.ok": "OK", "sh.bad": "FAIL",
        "sh.meas": "Recorded measurements", "sh.none_yet": "none yet", "sh.pending": "Pending measurements", "sh.none": "none",
        "sh.checklist": "Lockout checklist (ELEC-PLA-19): never work live",
        "sh.others": "Others working on the job now (each with their own padlock)", "sh.notes": "Circuit notes",
        "sh.tell": "When finished, tell the agent",
        "md.title": "# Work sheet: {c} · {n}", "md.info": "Job: {j} · Status: {s} · Assigned to: {a} · Survey of {d}",
        "md.img": "isolated plan of {c}", "md.lockout": "## Lock out before touching anything", "md.points": "## Outlet points ({n})",
        "md.meas": "## Measurements", "md.none_entered": "none entered", "md.pending": "Pending:",
        "md.checklist": "## Lockout checklist (never work live)", "md.others": "## Others working now",
        "md.notes": "## Notes", "md.finish": "## When finished", "md.not_proof": "The sheet does not prove that the circuit is dead.",
        "dxf.approx": "approx. {w} x {h} m", "dxf.approx1": "approx. {w} m", "dxf.floor": "Floor: {f}", "dxf.date": "Date: {d}  Source: {s}",
        "dxf.sketch": "Approximate sketch, not to scale", "dxf.meters": "Approximate dimensions, in meters",
        "dxf.layers": "One layer per circuit (CIRC_...): turn layers off to isolate a work sheet",
        "sl.short": "Single-line diagram", "sh.short": "Sheet {c}",
        "ct.OTHER": "OTHER",
        "new.floor": "Ground floor", "new.panel": "Main panel",
    },
    "ru": {
        "footer": "Ориентировочно, составлено по обследованию: не заменяет чертёж, подписанный аттестованным специалистом (ELEC-PLA-21)",
        "st.not_surveyed": "не обследована", "st.surveyed": "обследована", "st.measured": "измерена", "st.fault": "НЕИСПРАВНОСТЬ",
        "st.under_repair": "В РЕМОНТЕ", "st.repaired": "отремонтирована", "st.verified": "проверена",
        "pst.ok": "исправна", "pst.fault": "неисправна", "pst.doubtful": "сомнительна", "pst.unverified": "не проверена",
        "mt.insulation": "изоляция", "mt.pe_continuity": "непрерывность PE", "mt.rcd_trip": "срабатывание УЗО", "mt.voltage": "напряжение",
        "dev.MCB": "АВ", "dev.RCD": "УЗО", "dev.RCBO": "АВДТ", "dev.SWITCH": "ВН", "dev.FUSE": "ПР", "dev.SPD": "УЗИП", "dev.MPCB": "АЗД",
        "rcd_class": "тип {c}",
        "job_unnamed": "объект без названия", "job": "объект",
        "tb.floor": "Этаж: {f}", "tb.date": "Дата обследования: {d}", "tb.source": "Источник: {s}", "tb.drawn": "Начерчено в electricidad-plan · {d}",
        "tb.sketch": "Ориентировочный эскиз, не в масштабе", "tb.sketch2": "Размеры приблизительные (на глаз)", "tb.approx": "Размеры приблизительные",
        "plan.by_status": "{f} · цвет по состоянию", "plan.by_circuit": "{f} · цвет по цепям", "only": "только {ids}",
        "wet": "влажное", "north": "С", "no_circ": "б/ц",
        "legend": "Условные обозначения", "mark.fault": "неисправная точка", "mark.doubtful": "сомнительная точка",
        "runs_note": "Трассы схематичные: соединяют точки в порядке обследования и не показывают, где проходит труба. "
                     "Толстая линия: TUE, ACU, APM.",
        "line.under": "штрихи: подземная трасса (по примечанию к трассе)",
        "line.mbtf": "штрихпунктир: MBTF (сигнальные цепи, сверхнизкое напряжение)",
        "line.core": "линия с белой серединой: другая цепь того же цвета (больше 15 цепей)",
        "status_each": "Состояние каждой цепи", "circ_sheet": "Цепи этого листа", "circ_floor": "Цепи на этом этаже",
        "sl.title": "Однолинейная схема: сверху вниз, сеть → вводной аппарат → УЗО → автоматы → цепи",
        "sl.section_unknown": "сечение ?", "sl.to_panel": "→ щит {p}", "sl.more": "+{n} цепей ещё", "sl.no_circuit": "цепь не указана",
        "sl.also_feeds": "также питает: ", "sl.cycle": "{o}: циклическая ссылка", "panel": "щит",
        "sl.fed_from": "Питание от {u}", "sl.fed_in": " в щите {p}",
        "sl.utility": "Сеть энергоснабжающей организации: {s} → счётчик → главная линия → {t}",
        "sl.three": "трёхфазная 3×380/220 V", "sl.single": "однофазная 220 V",
        "sl.no_device": "Цепи без указанного защитного аппарата: ",
        "sl.ex.MCB": "Автоматический выключатель (АВ)", "sl.ex.RCD": "УЗО с функцией разъединения",
        "sl.ex.RCBO": "АВДТ (УЗО со встроенным автоматом)", "sl.ex.SWITCH": "Выключатель-разъединитель", "sl.ex.FUSE": "Предохранитель",
        "sl.ex.SPD": "Устройство защиты от импульсных перенапряжений (УЗИП)", "sl.ex.MPCB": "Автомат защиты двигателя",
        "sl.ticks": "Косые штрихи на линии = число полюсов. Цветной квадрат под каждой цепью = состояние:",
        "sl.symbols": "Символы: AEA 90364-7-771, приложение 771-K (на основе IEC 60617). Составлено по обследованию: проверьте на щите "
                      "перед использованием (реальный порядок перемычек и гребёнок может быть другим).",
        "sl.panels": "щиты {p}",
        "sh.pend.insulation": "Сопротивление изоляции мегаомметром, без напряжения, нагрузки отключены (ELEC-MED-4, ELEC-EQU-2)",
        "sh.pend.pe": "Непрерывность PE до каждой точки (ELEC-MED-3)",
        "sh.pend.rcd": "Срабатывание УЗО тестером из розетки этой цепи, при повторном включении (ELEC-MED-6)",
        "sh.no_label": "без надписи", "sh.lock": "{d} «{l}» ({t}) в щите {p} — {n}",
        "sh.no_device": "ЗАЩИТНЫЙ АППАРАТ НЕ УКАЗАН: работы запрещены, пока он не определён (ELEC-PLA-11)",
        "sh.none_entered": "не указаны", "sh.main": "вводной",
        "ck.1": "Отключить {d}, а если щит вскрывается или есть сомнения, то и вводной аппарат ({g}); входные клеммы вводного аппарата "
                "остаются под напряжением (ELEC-SEG-3).",
        "ck.2": "Личный замок и бирка на аппарате: один замок, один человек, один ключ; если работают несколько человек, многозамковая "
                "скоба (ELEC-SEG-4, ELEC-EQU-21).",
        "ck.3": "Проверить указатель напряжения на источнике под напряжением, проверить отсутствие напряжения В КАЖДОЙ КОРОБКЕ перед её "
                "вскрытием (L-N, L-PE, N-PE{x}) и снова проверить указатель (ELEC-SEG-5, ELEC-EQU-25).",
        "ck.3x": ", а также между фазами",
        "ck.4": "Общие коробки: любой провод другой цепи считать находящимся под напряжением (ELEC-PLA-16).",
        "ck.5": "Предупредить бригаду перед работой с мегаомметром: он тоже источник напряжения (ELEC-EQU-27).",
        "ck.6": "Выполнить оставшиеся измерения без напряжения и передать значения агенту (ELEC-MED-3, ELEC-MED-4, ELEC-PLA-20).",
        "ck.7": "По окончании: коробки закрыты, инструмент убран, снять только свой замок и сообщить; напряжение подаёт ответственный "
                "(ELEC-SEG-7, ELEC-EQU-17).",
        "ck.neutral": "Автомат может не разрывать нейтраль{x} или нейтраль сомнительна: заблокировать также вводной аппарат (ELEC-EQU-24).",
        "ck.neutral_x": " (не обследовано, двухполюсный ли он)",
        "sh.unassigned": "не назначен", "sh.name": "ИМЯ",
        "sh.title": "РАБОЧИЙ ЛИСТ · {c} · {n} · исполнитель: {a}", "sh.lockout": "ЗАБЛОКИРОВАТЬ, ПРЕЖДЕ ЧЕМ ЧТО-ЛИБО ТРОГАТЬ",
        "sh.upstream": "Выше по цепи: {u}",
        "sh.points": "Точки цепи {c} ({n})", "sh.no_points": "точки не указаны",
        "sh.heads": ["Точка", "Тип", "Помещение", "Высота", "Состояние", "Примечание"],
        "sh.ok": "НОРМА", "sh.bad": "НЕ НОРМА",
        "sh.meas": "Внесённые измерения", "sh.none_yet": "пока нет", "sh.pending": "Оставшиеся измерения", "sh.none": "нет",
        "sh.checklist": "Чек-лист отключения и блокировки (ELEC-PLA-19) — никогда не работать под напряжением",
        "sh.others": "Кто ещё сейчас работает на объекте (у каждого свой замок)", "sh.notes": "Примечания к цепи",
        "sh.tell": "По окончании сообщите агенту",
        "md.title": "# Рабочий лист — {c} · {n}", "md.info": "Объект: {j} · Состояние: {s} · Исполнитель: {a} · Обследование от {d}",
        "md.img": "отдельный план цепи {c}", "md.lockout": "## Заблокировать, прежде чем что-либо трогать", "md.points": "## Точки ({n})",
        "md.meas": "## Измерения", "md.none_entered": "не внесены", "md.pending": "Осталось:",
        "md.checklist": "## Чек-лист отключения и блокировки (никогда не работать под напряжением)", "md.others": "## Сейчас работают также",
        "md.notes": "## Примечания", "md.finish": "## По окончании", "md.not_proof": "Лист не доказывает, что цепь обесточена.",
        "dxf.approx": "прибл. {w} x {h} m", "dxf.approx1": "прибл. {w} m", "dxf.floor": "Этаж: {f}", "dxf.date": "Дата: {d}  Источник: {s}",
        "dxf.sketch": "Ориентировочный эскиз, не в масштабе", "dxf.meters": "Размеры приблизительные, в метрах",
        "dxf.layers": "Один слой на цепь (CIRC_...): отключая слои, получаете отдельный рабочий лист",
        "sl.short": "Однолинейная схема", "sh.short": "Лист {c}",
        "ct.OTHER": "ПРОЧЕЕ",
        "new.floor": "Первый этаж", "new.panel": "Главный щит",
    },
}
DECIMAL = {"es": ",", "ru": ",", "en": "."}
DXF_CODEPAGE = {"es": ("cp1252", "ANSI_1252"), "en": ("cp1252", "ANSI_1252"), "ru": ("cp1251", "ANSI_1251")}
_LANG = ["es"]                                    # language of the drawing being rendered (set by use_lang)


def pick_lang(arg=None):
    """Explicit --lang, else "lang" in the prefs file, else es (same rule as manual.py)."""
    if arg in LANGS:
        return arg
    try:
        v = json.load(open(PREFS)).get("lang")
    except (OSError, ValueError, AttributeError):
        v = None
    return v if v in LANGS else "es"


def use_lang(lang):
    _LANG[0] = lang if lang in LANGS else "es"
    return _LANG[0]


def tr(key, **kw):
    """Person-facing string in the current language (falls back to es)."""
    s = TXT[_LANG[0]].get(key)
    if s is None:
        s = TXT["es"][key]
    return s.format(**kw) if kw and isinstance(s, str) else s


def st_txt(status):
    return tr("st." + status) if status in STATUSES else str(status or "?")


def pst_txt(status):
    return tr("pst." + status) if status in POINT_STATUSES else str(status or "?")


def mt_txt(kind):
    return tr("mt." + kind) if kind in MEASUREMENT_TYPES else str(kind or "?")


def ct_txt(kind):
    return tr("ct." + kind) if kind == "OTHER" else str(kind or "?")


def dev_txt(kind):
    return tr("dev." + kind) if kind in DEVICE_TYPES else str(kind or "?")


# ---------------------------------------------------------------- symbols
# Each symbol is a list of primitives in local units (u ≈ 12 px on the plan, 0.15 m in the DXF), with y pointing up:
#   ("c", cx, cy, r, fill)  circle     ("l", x1, y1, x2, y2)  line      ("a", cx, cy, r, deg0, deg1)  arc
#   ("r", x, y, width, height, fill)   ("p", [(x, y), ...], closed, fill)      ("t", x, y, text, height)  centred text
# fill: None (empty), "s" (stroke colour), "w" (white). Symbols with orient=True rotate so that their local "down" points
# to the nearest wall of the room (wall light and socket outlets, as on a hand-drawn plan).
# Source of the shapes: the "Table of the most used symbols" in surveys-and-drawings.md (ELEC-PLA-4), which describes the IRAM 2010
# Sección IV symbols (old edition, reproduced in the UNCuyo course notes, Apéndice II) and their IEC 60617 part 11 equivalent.
# IRAM 2010 and the IEC 60617 database (paid / restricted access) could not be re-read when this was written: the shapes follow that table.
# The single-line diagram uses the switchgear symbols of Anexo 771-K of AEA 90364-7-771 Ed. 2006 ("Símbolos usuales", informative,
# based on IEC 60617; IEV 441-14-20 circuit breaker), read in the published text of the 771.
# Letters inside a symbol (AA, TT, B, M, EX, PE, D, S, E, IP, 20A) are part of the IRAM shape and stay the same in every language.
SYMBOLS = {
    "ceiling_light": {"name": {"es": "Boca de techo (centro)", "en": "Ceiling outlet point (center)", "ru": "Потолочная точка (центр)"},
                      "source": "IRAM 2010: filled dot (IEC 60617: lamp, circle with an X)",
                      "prims": [("c", 0, 0, 0.62, "s")]},
    "wall_light": {"name": {"es": "Aplique (boca de pared)", "en": "Wall light (wall outlet point)", "ru": "Бра (настенная точка)"},
                   "source": "IRAM 2010: filled dot with a stroke to the wall", "orient": True,
                   "prims": [("c", 0, 0.15, 0.6, "s"), ("l", 0, -0.45, 0, -1.1), ("l", -0.55, -1.1, 0.55, -1.1)]},
    "switch": {"name": {"es": "Llave de un punto", "en": "One-way switch", "ru": "Одноклавишный выключатель"},
               "source": "IRAM 2010 / IEC 60617: circle with an oblique stroke and a small tick",
               "prims": [("c", 0, 0, 0.42, "w"), ("l", 0.3, 0.3, 1.05, 1.05), ("l", 1.05, 1.05, 1.4, 0.7)]},
    "double_switch": {"name": {"es": "Llave de dos puntos", "en": "Two-gang switch", "ru": "Двухклавишный выключатель"},
                      "source": "IRAM 2010: circle with two strokes in a V",
                      "prims": [("c", 0, 0, 0.42, "w"), ("l", 0.15, 0.39, 0.45, 1.25), ("l", 0.45, 1.25, 0.85, 1.1),
                                ("l", 0.39, 0.15, 1.25, 0.45), ("l", 1.25, 0.45, 1.1, 0.05)]},
    "two_way_switch": {"name": {"es": "Llave de combinación", "en": "Two-way switch", "ru": "Проходной выключатель"},
                       "source": "IRAM 2010 / IEC 60617: crossed circle, a tick at each end",
                       "prims": [("c", 0, 0, 0.42, "w"), ("l", 0.3, 0.3, 1.05, 1.05), ("l", 1.05, 1.05, 1.4, 0.7),
                                 ("l", -0.3, -0.3, -1.05, -1.05), ("l", -1.05, -1.05, -1.4, -0.7)]},
    "socket": {"name": {"es": "Toma 2P+T 10 A", "en": "Socket outlet 2P+E 10 A", "ru": "Розетка 2P+PE 10 A"},
               "source": "IRAM 2010: arc with a stroke and a filled triangle (earth, IRAM 2071)", "orient": True,
               "prims": [("a", 0, -0.55, 0.75, 0, 180), ("l", 0, 0.2, 0, 0.75), ("p", [(-0.3, 0.75), (0.3, 0.75), (0, 1.2)], True, "s")]},
    "double_socket": {"name": {"es": "Toma doble 2P+T", "en": "Double socket outlet 2P+E", "ru": "Двойная розетка 2P+PE"},
                      "source": "IRAM 2010: two socket outlets together (IEC 60617: semicircle with two strokes)", "orient": True,
                      "prims": [("a", 0, -0.55, 0.75, 0, 180), ("l", -0.3, 0.13, -0.3, 0.75), ("l", 0.3, 0.13, 0.3, 0.75),
                                ("p", [(-0.45, 0.75), (0.45, 0.75), (0, 1.2)], True, "s"), ("t", 1.25, 0.2, "2", 0.9)]},
    "socket_20a": {"name": {"es": "Toma 20 A (uso especial)", "en": "20 A socket outlet (special use)", "ru": "Розетка 20 A (специальная)"},
                   "source": "IRAM 2010: motive power socket outlet, filled arc", "orient": True,
                   "prims": [("p", [(-0.75, -0.55)] + [(0.75 * math.cos(math.radians(a)), -0.55 + 0.75 * math.sin(math.radians(a)))
                                                      for a in range(180, -1, -15)], True, "s"),
                             ("l", 0, 0.2, 0, 0.75), ("p", [(-0.3, 0.75), (0.3, 0.75), (0, 1.2)], True, "s"), ("t", 1.55, 0.1, "20A", 0.65)]},
    "outdoor_socket": {"name": {"es": "Toma exterior (con IP)", "en": "Outdoor socket outlet (IP rated)", "ru": "Наружная розетка (со степенью IP)"},
                       "source": "IRAM 2010: protected socket outlet; IEC: socket outlet with IP rating", "orient": True,
                       "prims": [("a", 0, -0.55, 0.75, 0, 180), ("l", 0, 0.2, 0, 0.75), ("p", [(-0.3, 0.75), (0.3, 0.75), (0, 1.2)], True, "s"),
                                 ("c", 0, -0.2, 0.17, "s"), ("t", 1.35, 0.1, "IP", 0.7)]},
    "junction_box": {"name": {"es": "Caja de paso (no es boca)", "en": "Junction box (not an outlet point)", "ru": "Распаечная коробка (не точка)"},
                     "source": "IRAM 2010 / IEC 60617: small square",
                     "prims": [("r", -0.55, -0.55, 1.1, 1.1, "w")]},
    "ac": {"name": {"es": "Boca aire acondicionado", "en": "Air conditioner outlet point", "ru": "Точка кондиционера"},
           "source": "IRAM 2010: motive power outlet point (circle) with abbreviation",
           "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "AA", 0.7)]},
    "water_heater": {"name": {"es": "Termotanque eléctrico", "en": "Electric water heater", "ru": "Электрический водонагреватель"},
                     "source": "IRAM 2010: heating outlet point (circle) with abbreviation",
                     "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "TT", 0.7)]},
    "pump": {"name": {"es": "Bomba", "en": "Pump", "ru": "Насос"},
             "source": "IRAM 2010: motive power outlet point (circle) with abbreviation",
             "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "B", 0.9)]},
    "motor": {"name": {"es": "Motor (portón, etc.)", "en": "Motor (gate, etc.)", "ru": "Двигатель (ворота и т. п.)"},
              "source": "IRAM 2010 / IEC 60617: circle with M",
              "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "M", 0.9)]},
    "extractor_fan": {"name": {"es": "Extractor / ventilador", "en": "Exhaust fan", "ru": "Вытяжной вентилятор"},
                      "source": "IRAM 2010: outlet point (circle) with abbreviation; counts as a lighting outlet point (ELEC-CIR-6)",
                      "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "EX", 0.65)]},
    "door_phone": {"name": {"es": "Portero eléctrico", "en": "Door entry phone", "ru": "Домофон"},
                   "source": "IRAM 2010: PE in a rectangle",
                   "prims": [("r", -0.95, -0.6, 1.9, 1.2, "w"), ("t", 0, 0, "PE", 0.7)]},
    "doorbell": {"name": {"es": "Timbre (botón)", "en": "Doorbell (push button)", "ru": "Звонок (кнопка)"},
                 "source": "IRAM 2010: small circle with a dot",
                 "prims": [("c", 0, 0, 0.6, "w"), ("c", 0, 0, 0.2, "s")]},
    "tv": {"name": {"es": "Boca de TV", "en": "TV outlet point", "ru": "Телевизионная розетка"},
           "source": "IRAM 2010: circle with TV", "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "TV", 0.65)]},
    "data": {"name": {"es": "Boca de datos / teléfono", "en": "Data / telephone outlet point", "ru": "Розетка данных / телефона"},
             "source": "IRAM 2010: circle with T; here D", "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "D", 0.8)]},
    "sensor": {"name": {"es": "Sensor de movimiento", "en": "Motion sensor", "ru": "Датчик движения"},
               "source": "no symbol in the IRAM consulted: own symbol, always in the legend",
               "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "S", 0.85)]},
    "emergency_light": {"name": {"es": "Luz de emergencia", "en": "Emergency light", "ru": "Аварийный светильник"},
                        "source": "no symbol in the IRAM consulted: own symbol, always in the legend",
                        "prims": [("c", 0, 0, 0.95, "w"), ("t", 0, 0, "E", 0.85)]},
    "earth_rod": {"name": {"es": "Jabalina / puesta a tierra", "en": "Earth rod / earthing", "ru": "Заземлитель / заземление"},
                  "source": "IRAM 2010 / IEC 60417-5017: stroke with three decreasing bars",
                  "prims": [("l", 0, 1.0, 0, 0), ("l", -0.9, 0, 0.9, 0), ("l", -0.55, -0.35, 0.55, -0.35), ("l", -0.2, -0.7, 0.2, -0.7)]},
    "meter": {"name": {"es": "Medidor", "en": "Meter", "ru": "Счётчик"},
              "source": "IRAM 2010: M in a rounded-corner rectangle (meter box)",
              "prims": [("r", -1.0, -0.65, 2.0, 1.3, "w"), ("t", 0, 0, "M", 0.8)]},
    "_tp": {"name": {"es": "Tablero principal", "en": "Main panel", "ru": "Главный щит"},
            "source": "IRAM 2010: 1:3 rectangle with both diagonals (filled bow tie)",
            "prims": [("r", -1.5, -0.5, 3.0, 1.0, "w"), ("p", [(-1.5, -0.5), (-1.5, 0.5), (0, 0)], True, "s"),
                      ("p", [(1.5, -0.5), (1.5, 0.5), (0, 0)], True, "s"), ("l", -1.5, -0.5, 1.5, 0.5), ("l", -1.5, 0.5, 1.5, -0.5)]},
    "_ts": {"name": {"es": "Tablero seccional", "en": "Sub-panel", "ru": "Групповой щит"},
            "source": "IRAM 2010: 1:3 rectangle with one diagonal (half filled)",
            "prims": [("r", -1.5, -0.5, 3.0, 1.0, "w"), ("p", [(-1.5, -0.5), (1.5, -0.5), (1.5, 0.5)], True, "s")]},
    "_unknown": {"name": {"es": "Punto de tipo desconocido", "en": "Point of unknown type", "ru": "Точка неизвестного типа"},
                 "source": "own symbol", "prims": [("c", 0, 0, 0.9, "w"), ("t", 0, 0, "?", 0.9)]},
}


def sym_name(kind, lang=None):
    sym = SYMBOLS.get(kind) or SYMBOLS["_unknown"]
    return sym["name"].get(lang or _LANG[0]) or sym["name"]["es"]


class Usage(Exception):
    pass


# ---------------------------------------------------------------- helpers

def num(v):
    """Number from the JSON (accepts "3,5" as 3.5); None if it is not a finite number."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str):
        try:
            f = float(v.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return f if math.isfinite(f) and abs(f) < 1e6 else None


def fmt(x, nd=1, dec=None):
    """Number for a drawing: decimal comma in es/ru, point in en (dec forces one)."""
    if x is None:
        return "?"
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{x:.0f}"
    return s.replace(".", dec or DECIMAL[_LANG[0]])


def fnum(x, nd=1):
    """Number for tool output (the model reads it): always a decimal point."""
    return fmt(x, nd, ".")


def esc(s):
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(s))
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def slug(s, maxlen=60):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(s).strip()).strip("-.")
    return (s or "x")[:maxlen]


def lst(d, k):
    v = d.get(k)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def finding(check, rule, status, evidence, ref=None):
    f = {"check": check, "rule": rule, "status": status, "evidence": str(evidence)[:300]}
    if ref is not None:
        f["ref"] = str(ref)
    return f


def is_sketch(d):
    src = str(d.get("source", "")).lower()
    return any(w in src for w in SKETCH_WORDS)


def resolve(arg):
    """Path to the survey: the file, a folder holding survey.json, or the job name under ROOT."""
    if os.path.isfile(arg):
        return arg
    if os.path.isdir(arg) and os.path.isfile(os.path.join(arg, SURVEY)):
        return os.path.join(arg, SURVEY)
    if not arg.endswith(".json") and "/" not in arg:
        for name in dict.fromkeys((slug(arg.lower()), slug(arg))):   # `new` stores the folder in lower case
            p = os.path.join(ROOT, name, SURVEY)
            if os.path.isfile(p):
                return p
    raise Usage(f"Survey \"{arg}\" not found (neither as a file nor as a job in {ROOT}).")


def load(arg):
    path = resolve(arg)
    try:
        with open(path, encoding="utf-8-sig") as f:   # -sig: accepts the BOM some Windows editors leave
            d = json.load(f)
    except (OSError, UnicodeDecodeError) as e:
        raise Usage(f"Could not read {path}: {type(e).__name__}.")
    except json.JSONDecodeError as e:
        raise Usage(f"{path} is not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}.")
    except RecursionError:
        raise Usage(f"{path}: JSON nested too deep; not a survey.")
    if not isinstance(d, dict):
        raise Usage(f"{path}: the survey must be a JSON object.")
    return d, path


# Fields the code uses as text (dict keys, comparisons, labels). If they arrive as a list or object in the JSON, the rest of the
# program fails with TypeError: sanitize() returns a copy where they are text (numbers) or None (anything else), and the list of
# what it fixed so validate can report it. The original file is not touched.
TEXT_FIELDS = ("id", "floor", "room", "panel", "upstream", "device", "circuit", "type", "status", "class", "curve",
               "assigned_to", "letter", "label", "name", "note", "notes", "unit", "date")


def _txt(v):
    if v is None or isinstance(v, str):
        return v, True
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (str(v) if math.isfinite(v) else None), True
    return None, False


def sanitize(d):
    """(sanitized copy of the survey, [(collection, id or position, field), ...] with what was not text)."""
    probs = []
    out = dict(d)
    for k in ("job", "source", "date"):
        if k in out:
            v, ok = _txt(out[k])
            out[k] = v if v is not None else ""
            if not ok:
                probs.append(("survey", "-", k))
    if "supply" in out and not isinstance(out["supply"], dict):
        out["supply"] = {}
        probs.append(("survey", "-", "supply"))
    for col in ("floors", "rooms", "panels", "devices", "circuits", "points", "runs"):
        if not isinstance(out.get(col), list):
            continue
        new = []
        for n, o in enumerate(out[col]):
            if not isinstance(o, dict):
                probs.append((col, f"#{n + 1}", "(not an object)"))
                continue
            o = dict(o)
            for field in TEXT_FIELDS:
                if field in o:
                    v, ok = _txt(o[field])
                    o[field] = v
                    if not ok:
                        probs.append((col, o.get("id") if isinstance(o.get("id"), str) else f"#{n + 1}", field))
            if col == "runs" and "sequence" in o:
                seq = o["sequence"] if isinstance(o["sequence"], list) else []
                clean = [x for x in (_txt(e)[0] for e in seq) if x is not None]
                if len(clean) != len(seq) or not isinstance(o["sequence"], list):
                    probs.append((col, f"#{n + 1}", "sequence"))
                o["sequence"] = clean
            if col == "circuits" and "measurements" in o:
                meds = []
                for m in (o["measurements"] if isinstance(o["measurements"], list) else []):
                    if isinstance(m, dict):
                        m = dict(m)
                        for field in ("type", "unit", "date"):
                            if field in m:
                                m[field] = _txt(m[field])[0]
                        meds.append(m)
                o["measurements"] = meds
            new.append(o)
        out[col] = new
    return out, probs


def write_atomic(path, text, bak=False):
    """Write to a temp file in the same folder and rename it: a half-written file never remains. bak=True copies the old one to .bak."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):                  # mkstemp creates 0600: keep the previous file's mode
            os.chmod(tmp, os.stat(path).st_mode & 0o777)
        else:
            um = os.umask(0)
            os.umask(um)
            os.chmod(tmp, 0o666 & ~um)
        if bak and os.path.exists(path):          # the copy also goes through temp + rename: a .bak that is a symlink is not followed
            with open(path, "rb") as f:
                old = f.read()
            fdb, tmpb = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=d)
            try:
                with os.fdopen(fdb, "wb") as f:
                    f.write(old)
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(tmpb, os.stat(path).st_mode & 0o777)
                os.replace(tmpb, path + ".bak")
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmpb)
                raise
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_json(path, d):
    write_atomic(path, json.dumps(d, ensure_ascii=False, indent=1) + "\n", bak=True)


def indexes(d):
    ix = {}
    for k in ("floors", "rooms", "panels", "devices", "circuits", "points"):
        ix[k] = {}
        for o in lst(d, k):
            if isinstance(o.get("id"), str) and o["id"] not in ix[k]:
                ix[k][o["id"]] = o
    return ix


def xy(o):
    x, y = num(o.get("x")), num(o.get("y"))
    return (x, y) if x is not None and y is not None else None


def polygon(a):
    p = a.get("polygon")
    if not isinstance(p, list) or len(p) < 3:
        return None
    out = []
    for v in p:
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            return None
        x, y = num(v[0]), num(v[1])
        if x is None or y is None:
            return None
        out.append((x, y))
    return out if abs(area(out)) > 1e-6 else None


def area(p):
    return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))) / 2


def centroid(p):
    a = area(p)
    if abs(a) < 1e-9:
        return sum(v[0] for v in p) / len(p), sum(v[1] for v in p) / len(p)
    cx = sum((p[i][0] + p[(i + 1) % len(p)][0]) * (p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]) for i in range(len(p)))
    cy = sum((p[i][1] + p[(i + 1) % len(p)][1]) * (p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]) for i in range(len(p)))
    return cx / (6 * a), cy / (6 * a)


def inside(pt, p):
    x, y, ins = pt[0], pt[1], False
    for i in range(len(p)):
        (x1, y1), (x2, y2) = p[i], p[(i + 1) % len(p)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ins = not ins
    return ins


def nearest_wall(pt, p):
    """(distance, unit vector from the point to the nearest wall)."""
    best = (1e9, (0.0, -1.0))
    for i in range(len(p)):
        (x1, y1), (x2, y2) = p[i], p[(i + 1) % len(p)]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / L2))
        cx, cy = x1 + t * dx, y1 + t * dy
        dist = math.hypot(cx - pt[0], cy - pt[1])
        if dist < best[0]:
            best = (dist, ((cx - pt[0]) / dist, (cy - pt[1]) / dist) if dist > 1e-9 else (0.0, -1.0))
    return best


def chain(ix, dev_id, d):
    """Devices from dev_id upward, crossing from a sub-panel to the main panel through panel.upstream."""
    out, seen, cur = [], set(), dev_id
    while cur and cur not in seen:
        seen.add(cur)
        p = ix["devices"].get(cur)
        if not p:
            break
        out.append(p)
        nxt = p.get("upstream")
        if not nxt:
            t = ix["panels"].get(p.get("panel"))
            nxt = t.get("upstream") if t else None
            if nxt in ix["panels"]:                # the sub-panel says which panel feeds it, without the device: stop here
                nxt = None
        cur = nxt
    return out


def is_rcd30(p):
    idn = num(p.get("idn_ma"))
    return p.get("type") in ("RCD", "RCBO") and idn is not None and idn <= 30


def points_of(d, cid):
    return [p for p in lst(d, "points") if p.get("circuit") == cid]


def outlets(d, cid):
    return sum(1 for p in points_of(d, cid) if p.get("type") not in NOT_OUTLET)


def conductors(d, ix, c):
    s, pe = num(c.get("section_mm2")), num(c.get("pe_mm2"))
    if s is None:
        return ""
    p = ix["devices"].get(c.get("device")) or {}
    n = int(num(p.get("poles")) or 2)
    n = 2 if n < 2 else n
    return f"{n}x{fmt(s)}" + (f"+T{fmt(pe)}" if pe else "")


def dev_label(p):
    """Device as printed on a drawing, e.g. "PIA 2P C10" (es) / "MCB 2P C10" (en); "ID 2P 40 A 30 mA clase A"."""
    if not p:
        return "?"
    t = p.get("type", "?")
    pol = f"{int(num(p.get('poles')))}P " if num(p.get("poles")) else ""
    i = num(p.get("in_a"))
    if t in ("MCB", "RCBO", "MPCB") and p.get("curve"):
        core = f"{p.get('curve')}{fmt(i, 0) if i else '?'}"
    else:
        core = f"{fmt(i, 0)} A" if i else "? A"
    s = f"{dev_txt(t)} {pol}{core}"
    if t in ("RCD", "RCBO"):
        s += f" {fmt(num(p.get('idn_ma')), 0)} mA" + (" " + tr("rcd_class", c=p["class"]) if p.get("class") else "")
    return s


# ---------------------------------------------------------------- validate

def validate(d):
    F = []
    add = lambda *a, **k: F.append(finding(*a, **k))
    for k in ("floors", "rooms", "panels", "devices", "circuits", "points", "runs"):
        if k in d and not isinstance(d[k], list):
            add("structure", "surveys-and-drawings.md", "fail", f"\"{k}\" must be a list")
    d, probs = sanitize(d)
    for col, oid, field in probs[:20]:
        if field.startswith("("):
            add("data_type", "surveys-and-drawings.md", "fail", f"{col} {oid}: each element must be an object {{...}}; ignored", ref=oid)
        else:
            add("data_type", "surveys-and-drawings.md", "fail", f"{col} {oid}: \"{field}\" must be text (got a list, an object or "
                "a boolean); ignored for drawing", ref=oid)
    if len(probs) > 20:
        add("data_type", "surveys-and-drawings.md", "fail", f"and {len(probs) - 20} more fields with the wrong data type")
    if d.get("version") != VERSION:
        add("version", "surveys-and-drawings.md", "fail", f"version must be {VERSION} (got {d.get('version')!r})")
    job = str(d.get("job", ""))
    if not job.strip():
        add("job", "surveys-and-drawings.md", "warn", "the short job name is missing")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|\d[\d \-]{7,}\d", job):
        add("personal_data", "surveys-and-drawings.md", "warn", "the job name looks like it has an email or a phone number: use a short name with no personal data")
    sup = d.get("supply") if isinstance(d.get("supply"), dict) else {}
    if sup.get("type") not in SUPPLY_TYPES:
        add("supply", "ELEC-REV-4", "warn", f"supply.type unknown ({' or '.join(SUPPLY_TYPES)})")
    ix = indexes(d)

    # ids: unique across the whole survey (runs mix panels and points), except floors, which have their own
    seen = {}
    for k in ("rooms", "panels", "devices", "circuits", "points"):
        for o in lst(d, k):
            i = o.get("id")
            if not isinstance(i, str) or not i.strip():
                add("missing_id", "ELEC-PLA-5", "fail", f"an element of \"{k}\" has no id", ref=k)
                continue
            if i in seen:
                add("duplicate_id", "ELEC-PLA-5", "fail", f"the id \"{i}\" is repeated ({seen[i]} and {k})", ref=i)
            else:
                seen[i] = k
    fs = set()
    for o in lst(d, "floors"):
        if o.get("id") in fs:
            add("duplicate_id", "ELEC-PLA-5", "fail", f"the floor \"{o.get('id')}\" is repeated", ref=o.get("id"))
        fs.add(o.get("id"))
    if not ix["floors"]:
        add("floors", "surveys-and-drawings.md", "fail", "there is no floor (at least {\"id\": \"PB\"})")

    def ref(obj_id, field, value, collection, required=True, extra=()):
        if value in (None, ""):
            if required:
                add("broken_reference", "surveys-and-drawings.md", "fail", f"{obj_id}: \"{field}\" is missing", ref=obj_id)
            return False
        if value not in ix[collection] and value not in extra:
            add("broken_reference", "surveys-and-drawings.md", "fail", f"{obj_id}: \"{field}\" = \"{value}\" does not exist in {collection}", ref=obj_id)
            return False
        return True

    room_poly = {}
    for a in lst(d, "rooms"):
        ref(a.get("id"), "floor", a.get("floor"), "floors")
        p = polygon(a)
        if p is None:
            add("polygon", "ELEC-PLA-7", "fail", f"{a.get('id')}: the polygon needs 3 or more vertices [[x,y],...] in meters and an area", ref=a.get("id"))
        else:
            room_poly[a.get("id")] = p
            side = max(max(v[0] for v in p) - min(v[0] for v in p), max(v[1] for v in p) - min(v[1] for v in p))
            if side > 150:
                add("scale", "ELEC-PLA-7", "warn", f"{a.get('id')}: it is {fnum(side, 0)} m on a side; coordinates are in METERS "
                    "(were they entered in centimeters?)", ref=a.get("id"))
    for t in lst(d, "panels"):
        ref(t.get("id"), "floor", t.get("floor"), "floors")
        if xy(t) is None:
            add("coordinates", "ELEC-PLA-7", "warn", f"{t.get('id')}: the panel has no x, y (not drawn on the plan)", ref=t.get("id"))
        if t.get("upstream"):
            ref(t.get("id"), "upstream", t.get("upstream"), "devices", extra=ix["panels"])

    for p in lst(d, "devices"):
        pid = p.get("id")
        ref(pid, "panel", p.get("panel"), "panels")
        if p.get("upstream"):
            if ref(pid, "upstream", p.get("upstream"), "devices") and p.get("upstream") == pid:
                add("broken_reference", "surveys-and-drawings.md", "fail", f"{pid} is upstream of itself", ref=pid)
        if p.get("type") not in DEVICE_TYPES:
            add("unknown_value", "surveys-and-drawings.md", "warn", f"{pid}: type \"{p.get('type')}\" (valid: {', '.join(DEVICE_TYPES)})", ref=pid)
        if p.get("type") in ("RCD", "RCBO"):
            idn = num(p.get("idn_ma"))
            if idn is None:
                add("rcd_missing_data", "ELEC-REV-6", "warn", f"{pid}: RCD with no IΔn (idn_ma): it cannot be confirmed to be 30 mA", ref=pid)
            if not p.get("class"):
                add("rcd_missing_data", "ELEC-PRO-9", "warn", f"{pid}: the RCD class is missing (AC, A, F or B)", ref=pid)
        if p.get("type") in ("MCB", "RCBO", "SWITCH", "MPCB", "FUSE", "RCD") and num(p.get("in_a")) is None:
            add("unknown_in", "ELEC-REV-5", "warn", f"{pid}: In unreadable or not entered (label \"{p.get('label', '')}\")", ref=pid)
        if p.get("type") == "FUSE":
            add("fuse", "ELEC-PRO-20", "warn", f"{pid}: fuse as circuit protection; dwellings use IEC 60898-1 MCBs", ref=pid)
    # upstream cycles
    for p in lst(d, "devices"):
        seen_, cur = set(), p.get("id")
        while cur in ix["devices"] and cur not in seen_:
            seen_.add(cur)
            cur = ix["devices"][cur].get("upstream")
        if cur in seen_ and cur is not None:
            add("cycle", "surveys-and-drawings.md", "fail", f"{p.get('id')}: the upstream chain forms a cycle", ref=p.get("id"))
            break

    # RCDs: how many circuits hang from each one and whether its In is enough
    under_rcd = {}
    for c in lst(d, "circuits"):
        for q in chain(ix, c.get("device"), d):
            if q.get("type") in ("RCD", "RCBO"):
                under_rcd.setdefault(q["id"], []).append(c)
                break
    for iid, cs in under_rcd.items():
        if len(cs) > 3:
            add("single_rcd", "ELEC-REV-10", "warn",
                f"{iid} protects {len(cs)} circuits: the sum of leakages makes it trip and one fault leaves everything dark; the guide's "
                f"criterion is 2 to 3 per RCD, outdoor and pool on their own (ELEC-EQU-7, ELEC-PRO-11)", ref=iid)
        q = ix["devices"][iid]
        iin = num(q.get("in_a"))
        if iin:
            above = [x for x in chain(ix, iid, d)[1:] if x.get("type") in ("MCB", "SWITCH", "MPCB", "FUSE", "RCBO") and num(x.get("in_a"))]
            kids = [x for x in lst(d, "devices") if x.get("upstream") == iid and num(x.get("in_a"))]
            total = sum(num(x.get("in_a")) for x in kids)
            if not (above and num(above[0].get("in_a")) <= iin) and total > iin:
                add("rcd_in", "ELEC-PRO-10", "warn", f"{iid}: In {fnum(iin, 0)} A lower than the sum of its MCBs ({fnum(total, 0)} A) and no MCB "
                    f"upstream that covers it", ref=iid)
        motors = [c for c in cs if c.get("type") in ("ACU", "APM") or any(p.get("type") in ("ac", "pump", "motor") for p in points_of(d, c.get("id")))]
        if q.get("class") == "AC" and motors:
            add("rcd_class", "ELEC-PRO-9", "warn", f"{iid} is class AC and feeds {', '.join(c['id'] for c in motors[:4])} (air conditioner, pump or "
                "motor): with power electronics it must be type A or F", ref=iid)

    for c in lst(d, "circuits"):
        cid = c.get("id")
        kind = c.get("type")
        if kind not in CIRCUIT_TYPES:
            add("unknown_value", "surveys-and-drawings.md", "warn", f"{cid}: type \"{kind}\" (valid: {', '.join(CIRCUIT_TYPES)})", ref=cid)
        if (c.get("status") or "not_surveyed") not in STATUSES:
            add("unknown_value", "ELEC-EQU-14", "warn", f"{cid}: status \"{c.get('status')}\" (valid: {', '.join(STATUSES)})", ref=cid)
        if not c.get("device"):
            add("no_device", "ELEC-PRO-1", "fail", f"{cid}: circuit with no protective device entered", ref=cid)
            dev = None
        elif ref(cid, "device", c.get("device"), "devices"):
            dev = ix["devices"][c["device"]]
            if dev.get("type") in ("RCD", "SWITCH", "SPD"):
                add("no_overcurrent", "ELEC-PRO-1", "fail", f"{cid} hangs directly from {dev['id']} ({dev.get('type')}): it has no "
                    "overload and short-circuit protection", ref=cid)
            ch = chain(ix, dev["id"], d)
            if not any(is_rcd30(q) for q in ch):   # MBTF too: the 220 V side is a final circuit
                unsure = [q["id"] for q in ch if q.get("type") in ("RCD", "RCBO") and num(q.get("idn_ma")) is None]
                if unsure:
                    # there is an RCD but its IΔn is unknown: missing data, not "no RCD"; it still blocks the sheets (ELEC-PLA-18)
                    add("rcd30_unconfirmed", "ELEC-PRO-7", "fail",
                        f"{cid}: there is an RCD upstream ({', '.join(unsure)}) but no IΔn entered: it cannot be confirmed to be 30 mA. "
                        "This is missing data: read the rating plate (ELEC-REV-26) or test it; do not enter 30 mA without seeing it", ref=cid)
                else:
                    add("no_rcd30", "ELEC-PRO-7", "fail", f"{cid}: there is no 30 mA RCD upstream of {dev['id']}", ref=cid)
        else:
            dev = None
        s = num(c.get("section_mm2"))
        cap = CAPS.get(kind, (None, None, None, None))
        if s is None:
            add("unknown_section", "ELEC-REV-11", "warn", f"{cid}: cross-section not entered, cannot check that the MCB protects the cable", ref=cid)
        else:
            smin = cap[3]
            if kind == "IUG" and any(p.get("type") in SOCKETS for p in points_of(d, cid)):
                smin = 2.5
            if smin and s < smin:
                add("min_section", "ELEC-CON-5", "fail", f"{cid}: {fnum(s)} mm² is less than the minimum for a {kind} ({fnum(smin)} mm², {CAPS_SOURCE})", ref=cid)
        pe = num(c.get("pe_mm2"))
        if pe is not None and pe < PE_MIN:
            add("small_pe", "ELEC-CON-6", "warn", f"{cid}: PE of {fnum(pe)} mm²; the minimum is {fnum(PE_MIN)} mm² (AEA 770.14.4.5)", ref=cid)
        elif pe is not None and s is not None and s <= 16 and pe < s:
            add("small_pe", "ELEC-CON-6", "warn", f"{cid}: PE of {fnum(pe)} mm² with a {fnum(s)} mm² phase; up to 16 mm² the PE equals the "
                "phase (AEA 770, table 770.14.I)", ref=cid)
        if dev is not None:
            i = num(dev.get("in_a"))
            if i is not None and s is not None:
                row = IZ_B1.get(s)
                if row is None:
                    add("odd_section", "ELEC-CON-8", "warn", f"{cid}: cross-section {fnum(s)} mm² outside the internal table", ref=cid)
                else:
                    iz = row[1] if (num(dev.get("poles")) or 2) >= 3 else row[0]
                    if i > iz:
                        add("mcb_over_cable", "ELEC-PRO-4", "fail", f"{cid}: {dev['id']} of {fnum(i, 0)} A on a {fnum(s)} mm² cable (Iz {iz} A, "
                            f"{IZ_SOURCE}): the MCB does not protect the cable (ELEC-REV-11)", ref=cid)
            if i is not None and cap[2] and i > cap[2]:
                add("mcb_over_type", "ELEC-CIR-5", "fail", f"{cid}: {dev['id']} of {fnum(i, 0)} A exceeds the cap for a {kind} ({cap[2]} A)", ref=cid)
        nb = outlets(d, cid)
        if cap[0] and nb > cap[0]:
            add("outlet_count", "ELEC-CIR-5", "fail", f"{cid}: {nb} outlet points; a {kind} allows {cap[0]} ({CAPS_SOURCE}; count per ELEC-CIR-6)", ref=cid)
        elif cap[1] and nb > cap[1]:
            add("outlet_count", "ELEC-CIR-5", "warn", f"{cid}: {nb} outlet points; the 771 allows {cap[1]} in a {kind} (the 770 up to {cap[0]})", ref=cid)
        st = c.get("status")
        asg = str(c.get("assigned_to") or "").strip()
        if st == "under_repair" and not asg:
            add("unassigned", "ELEC-EQU-14", "warn", f"{cid} is under repair with no technician assigned: someone may be working inside "
                "and nobody knows (ELEC-PLA-20, ELEC-SEG-4)", ref=cid)
        meds = [m for m in c.get("measurements", []) if isinstance(m, dict)] if isinstance(c.get("measurements"), list) else []
        for m in meds:
            if m.get("type") not in MEASUREMENT_TYPES:
                add("unknown_value", "ELEC-PLA-20", "warn", f"{cid}: measurement of type \"{m.get('type')}\"", ref=cid)
            if num(m.get("value")) is None:
                add("measurement", "ELEC-PLA-20", "warn", f"{cid}: {m.get('type')} measurement with no numeric value", ref=cid)
        if st == "verified":
            kinds_ok = {m.get("type") for m in meds if m.get("ok") is True}
            missing = [t for t in ("insulation", "pe_continuity") if t not in kinds_ok]
            if missing:
                add("verified_not_measured", "ELEC-PLA-20", "warn", f"{cid} is verified without {' or '.join(missing)} measured and ok (ELEC-MED-3, ELEC-MED-4)", ref=cid)
            if any(m.get("ok") is False for m in meds):
                add("verified_with_fault", "ELEC-MED-16", "warn", f"{cid} is verified but has a bad measurement entered", ref=cid)
            if any(p.get("status") == "fault" for p in points_of(d, cid)):
                add("verified_with_fault", "ELEC-MED-16", "warn", f"{cid} is verified with outlet points in fault", ref=cid)

    for p in lst(d, "points"):
        pid = p.get("id")
        ref(pid, "floor", p.get("floor"), "floors")
        kind = p.get("type")
        if kind not in POINT_TYPES:
            add("unknown_value", "ELEC-PLA-4", "warn", f"{pid}: type \"{kind}\" (drawn with \"?\")", ref=pid)
        if p.get("status") and p.get("status") not in POINT_STATUSES:
            add("unknown_value", "ELEC-PLA-20", "warn", f"{pid}: status \"{p.get('status')}\" (valid: {', '.join(POINT_STATUSES)})", ref=pid)
        circ = p.get("circuit")
        if circ:
            ref(pid, "circuit", circ, "circuits")
        elif kind not in NO_CIRCUIT_OK:
            add("point_no_circuit", "ELEC-PLA-5", "warn", f"{pid} ({kind}) has no circuit: identify it by switching off one MCB at a time (ELEC-PLA-11)", ref=pid)
        if kind in SWITCHES and not p.get("letter"):
            add("switch_no_letter", "ELEC-PLA-5", "warn", f"{pid}: switch with no letter; put the same letter on the switch and on its outlet points", ref=pid)
        pt = xy(p)
        if pt is None:
            add("coordinates", "ELEC-PLA-7", "fail", f"{pid}: x, y missing (meters)", ref=pid)
        room = p.get("room")
        if room:
            if ref(pid, "room", room, "rooms") and pt:
                a = ix["rooms"][room]
                if a.get("floor") != p.get("floor"):
                    add("floor_mismatch", "ELEC-PLA-7", "fail", f"{pid} is on floor {p.get('floor')} but its room {room} is on {a.get('floor')}", ref=pid)
                poly = room_poly.get(room)
                if poly and not inside(pt, poly):
                    dist = nearest_wall(pt, poly)[0]
                    if dist > OUTSIDE_TOL:
                        add("point_outside", "ELEC-PLA-7", "warn", f"{pid} ({fnum(pt[0], 2)}; {fnum(pt[1], 2)}) falls {fnum(dist, 1)} m outside {room}: "
                            "check the coordinates or the room", ref=pid)
        if kind in SOCKETS and circ in ix["circuits"]:
            a = ix["rooms"].get(room) or {}
            c = ix["circuits"][circ]
            if (a.get("wet") or kind == "outdoor_socket") and not any(is_rcd30(q) for q in chain(ix, c.get("device"), d)):
                add("wet_socket_no_rcd", "ELEC-PRO-7", "fail", f"{pid}: socket outlet in a wet or outdoor location with no 30 mA RCD (ELEC-ESP-4, ELEC-CIR-11)", ref=pid)
            if kind == "outdoor_socket" and c.get("type") in ("IUG", "TUG"):
                add("outdoor_socket_general", "ELEC-CIR-11", "warn", f"{pid}: outdoor socket outlet on a {c.get('type')}; in the 771 it goes on a TUE "
                    "(general-use circuits only allow outlet points in semi-covered areas, IP44)", ref=pid)

    for n, r in enumerate(lst(d, "runs")):
        cid = r.get("circuit")
        ok = ref(f"run {n + 1}", "circuit", cid, "circuits")
        seq = r.get("sequence")
        if not isinstance(seq, list) or len(seq) < 2:
            add("run", "ELEC-PLA-5", "warn", f"run {n + 1} ({cid}): the sequence needs 2 or more elements", ref=cid)
            continue
        for k, e in enumerate(seq):
            if e in ix["panels"]:
                continue
            if e not in ix["points"]:
                add("broken_reference", "surveys-and-drawings.md", "fail", f"run {n + 1} ({cid}): \"{e}\" is neither a panel nor a point", ref=cid)
            elif ok and ix["points"][e].get("circuit") not in (cid, None):
                add("mixed_run", "ELEC-PLA-15", "warn", f"the run of {cid} goes through {e}, which belongs to circuit "
                    f"{ix['points'][e].get('circuit')} (shared box or common neutral? ELEC-EQU-5)", ref=cid)
        if seq[0] not in ix["panels"]:
            add("run", "ELEC-PLA-5", "warn", f"run {n + 1} ({cid}) does not start at a panel", ref=cid)
    F.sort(key=lambda f: (ORDER.get(f["status"], 9), f["check"]))
    return F


# ---------------------------------------------------------------- SVG: primitives

def T(x, y, s, size=16, anchor="start", weight="normal", fill="#111", halo=False, rot=None, italic=False):
    tf = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot else ""
    st = ' font-style="italic"' if italic else ""
    base = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}"{st}{tf}'
    out = ""
    if halo:                                       # halo drawn separately: some renderers ignore paint-order
        out = f'<text {base} fill="#fff" stroke="#fff" stroke-width="{max(3, size / 4):.1f}" stroke-linejoin="round">{esc(s)}</text>'
    return out + f'<text {base} fill="{fill}">{esc(s)}</text>'


def rot_xy(u, v, ang):
    c, s = math.cos(ang), math.sin(ang)
    return u * c - v * s, u * s + v * c


def prim_points(pr, ang):
    """Primitive → polyline in rotated local units (arcs approximated)."""
    k = pr[0]
    if k == "a":
        _, cx, cy, r, a0, a1 = pr
        n = max(6, int(abs(a1 - a0) / 12))
        return [rot_xy(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)), ang) for i in range(n + 1)]
    if k == "l":
        return [rot_xy(pr[1], pr[2], ang), rot_xy(pr[3], pr[4], ang)]
    if k == "r":
        _, x, y, w, h, _f = pr
        return [rot_xy(*q, ang) for q in ((x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y))]
    if k == "p":
        pts = [rot_xy(a, b, ang) for a, b in pr[1]]
        return pts + ([pts[0]] if pr[2] else [])
    return []


def symbol_svg(kind, X, Y, u, color, sw=2.4, ang=0.0, opacity=1.0, backdrop=True):
    sym = SYMBOLS.get(kind) or SYMBOLS["_unknown"]
    if not sym.get("orient"):
        ang = 0.0
    out = [f'<g opacity="{opacity:.2f}">']
    if backdrop:
        out.append(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="{1.25 * u:.1f}" fill="#fff" fill-opacity="0.85"/>')
    fillc = lambda f: {"s": color, "w": "#fff"}.get(f, "none")
    for pr in sym["prims"]:
        k = pr[0]
        if k == "c":
            cx, cy = rot_xy(pr[1], pr[2], ang)
            out.append(f'<circle cx="{X + cx * u:.1f}" cy="{Y - cy * u:.1f}" r="{pr[3] * u:.1f}" fill="{fillc(pr[4])}" stroke="{color}" stroke-width="{sw}"/>')
        elif k == "t":
            tx, ty = rot_xy(pr[1], pr[2], ang)
            fs = pr[4] * u
            out.append(f'<text x="{X + tx * u:.1f}" y="{Y - ty * u + 0.36 * fs:.1f}" font-size="{fs:.1f}" text-anchor="middle" '
                       f'font-weight="bold" fill="{color}">{esc(pr[3])}</text>')
        else:
            pts = " ".join(f"{X + a * u:.1f},{Y - b * u:.1f}" for a, b in prim_points(pr, ang))
            f = fillc(pr[5]) if k == "r" else (fillc(pr[3]) if k == "p" else "none")
            out.append(f'<polyline points="{pts}" fill="{f}" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>')
    out.append("</g>")
    return "".join(out)


def svg_doc(E, W, H, title):
    # ImageMagick 7 (its internal MSVG renderer) does not draw the stroke unless stroke-opacity is explicit: added to everything with
    # a stroke (and it has to come AFTER stroke="...", otherwise it is ignored)
    E = [re.sub(r'(<(?:line|polyline|polygon|circle|rect|ellipse|path|text)\b(?![^>]*stroke-opacity)[^>]*?\sstroke="[^"]*")', r'\1 stroke-opacity="1"', e)
         for e in E]
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
            f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="{FONT}">\n<title>{esc(title)}</title>\n'
            f'<rect x="0" y="0" width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>\n' + "\n".join(E) + "\n</svg>\n")


def hatch(poly, color, step=16):
    """45° lines clipped to the polygon (in px), as a single <path>."""
    segs = []
    cs = [x - y for x, y in poly]
    c = math.floor(min(cs) / step) * step + step
    while c < max(cs):
        xs = []
        for i in range(len(poly)):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
            d1, d2 = x1 - y1 - c, x2 - y2 - c
            if (d1 > 0) != (d2 > 0):
                t = d1 / (d1 - d2)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            segs.append(f"M{a:.1f} {a - c:.1f}L{b:.1f} {b - c:.1f}")
        c += step
    return f'<path d="{" ".join(segs)}" fill="none" stroke="{color}" stroke-width="1.6"/>' if segs else ""


def text_width(s, size):
    return len(str(s)) * size * 0.58


def collides(b, boxes):
    return any(not (b[2] <= o[0] or b[0] >= o[2] or b[3] <= o[1] or b[1] >= o[3]) for o in boxes)


def cut(s, n):
    s = str(s)
    return s if len(s) <= n else s[:max(1, n - 1)] + "…"


def wrap(s, n):
    out, line = [], ""
    for w in str(s).split():
        if line and len(line) + 1 + len(w) > n:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out or [""]


def circ_style(d, c, ci, mode):
    color = STATUS_COLOR.get(c.get("status"), "#9E9E9E") if mode == "status" else PALETTE[ci % len(PALETTE)]
    width = 5.0 if c.get("type") in THICK else 3.0
    dash = "12 4 2 4" if c.get("type") == "MBTF" else ""
    return color, width, dash


def white_core(c, ci, mode):
    """With more circuits than colors, the second round of the palette is drawn with a white center: two circuits of the same color
    are not confused (no dotted line, because dash-dot and dashes already mean MBTF and underground, IRAM 2010)."""
    return mode == "circuit" and (ci // len(PALETTE)) % 2 == 1


def title_block(E, x, y, w, d, floor_name, extra=""):
    """Title block: job, floor, date, source, scale; returns the height used."""
    source = str(d.get("source", ""))
    sketch = is_sketch(d)
    h = 150
    E.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff" stroke="#222" stroke-width="2"/>')
    E.append(f'<line x1="{x + w * 0.55:.0f}" y1="{y}" x2="{x + w * 0.55:.0f}" y2="{y + h}" stroke="#222" stroke-width="1.2"/>')
    E.append(T(x + 14, y + 32, cut(d.get("job") or tr("job_unnamed"), 48), 24, weight="bold"))
    E.append(T(x + 14, y + 60, cut(tr("tb.floor", f=floor_name) + (f" · {extra}" if extra else ""), 62), 18))
    E.append(T(x + 14, y + 86, tr("tb.date", d=d.get("date") or "?"), 17))
    E.append(T(x + 14, y + 112, cut(tr("tb.source", s=source or "?"), 62), 17))
    E.append(T(x + 14, y + 137, tr("tb.drawn", d=AS_OF), 14, fill="#555"))
    xr = x + w * 0.55 + 14
    if sketch:
        E.append(T(xr, y + 36, tr("tb.sketch"), 22, weight="bold", fill="#B00020"))
        E.append(T(xr, y + 62, tr("tb.sketch2"), 16, fill="#B00020"))
    else:
        E.append(T(xr, y + 36, tr("tb.approx"), 20, weight="bold"))
    for i, ln in enumerate(wrap(tr("footer"), 52)[:3]):
        E.append(T(xr, y + 90 + i * 19, ln, 14, fill="#333"))
    return h


# ---------------------------------------------------------------- floor plan

def floors_of(d, floor=None):
    fs = [p["id"] for p in lst(d, "floors") if isinstance(p.get("id"), str)]
    if floor:
        if floor not in fs:
            raise Usage(f"There is no floor \"{floor}\". Floors: {', '.join(fs) or 'none'}.")
        return [floor]
    return fs


def render_plan(d, floor_id, mode="circuit", only=None, title=None, W=WIDTH):
    ix = indexes(d)
    floor = ix["floors"].get(floor_id, {"id": floor_id})
    fname = floor.get("name") or floor_id
    only = set(only or [])
    rooms = [(a, polygon(a)) for a in lst(d, "rooms") if a.get("floor") == floor_id]
    rooms = [(a, p) for a, p in rooms if p]
    pts = [p for p in lst(d, "points") if p.get("floor") == floor_id and xy(p)]
    tabs = [t for t in lst(d, "panels") if t.get("floor") == floor_id and xy(t)]
    circ_ix = {c.get("id"): (i, c) for i, c in enumerate(lst(d, "circuits"))}
    xs = [v[0] for _, p in rooms for v in p] + [xy(o)[0] for o in pts + tabs]
    ys = [v[1] for _, p in rooms for v in p] + [xy(o)[1] for o in pts + tabs]
    if not xs:
        xs, ys = [0, 10], [0, 8]
    minx, maxx, miny, maxy = min(xs) - 0.6, max(xs) + 0.6, min(ys) - 0.6, max(ys) + 0.6
    wm, hm = max(maxx - minx, 1), max(maxy - miny, 1)
    ML, MR, MT = 100, 40, 118
    PW = W - ML - MR
    s = min(PW / wm, 1750 / hm, 170)
    ox = ML + (PW - wm * s) / 2
    X = lambda x: ox + (x - minx) * s
    Y = lambda y: MT + (maxy - y) * s
    u = max(8.0, min(13.0, 0.17 * s))
    E, boxes = [], []
    tit = title or (tr("plan.by_status" if mode == "status" else "plan.by_circuit", f=fname)
                    + (" · " + tr("only", ids=", ".join(sorted(only))) if only else ""))
    E.append(T(28, 48, cut(d.get("job") or tr("job"), 60), 32, weight="bold"))
    E.append(T(28, 84, cut(tit, 110), 22, fill="#333"))

    def visible(cid):
        return not only or cid in only

    # rooms
    for a, p in rooms:
        pts_s = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in p)
        E.append(f'<polygon points="{pts_s}" fill="#F7F5EF" stroke="none"/>')
        if a.get("wet"):                           # hatching computed by hand: not every renderer draws <pattern>
            E.append(hatch([(X(x), Y(y)) for x, y in p], "#9CC3E0"))
    for a, p in rooms:
        pts_s = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in p)
        E.append(f'<polygon points="{pts_s}" fill="none" stroke="#333" stroke-width="4" stroke-linejoin="miter"/>')
    # boxes taken by symbols, before placing texts
    for o in pts + tabs:
        x, y = xy(o)
        r = (2.0 if o in tabs else 1.4) * u
        boxes.append((X(x) - r, Y(y) - r, X(x) + r, Y(y) + r))
    for a, p in rooms:
        cx, cy = centroid(p)
        bw, bh = max(v[0] for v in p) - min(v[0] for v in p), max(v[1] for v in p) - min(v[1] for v in p)
        name = cut(a.get("name") or a.get("id"), 22)
        dims = f"≈ {fmt(bw)} × {fmt(bh)} m" + (" · " + tr("wet") if a.get("wet") else "")
        size = 20 if bw * s > 150 else 16
        wbox = max(text_width(name, size), text_width(dims, 14)) / 2 + 4
        best = None
        for dy in (0, -0.8, 0.8, -1.6, 1.6, -2.4, 2.4, -3.2, 3.2):
            for dx in (0, -0.8, 0.8, -2.0, 2.0, -4.0, 4.0):
                bx, by = X(cx + dx), Y(cy + dy)
                b = (bx - wbox, by - size - 2, bx + wbox, by + 20)
                if not collides(b, boxes) and inside((cx + dx, cy + dy), p) and not any(
                        q is not p and abs(area(q)) < abs(area(p)) and inside((cx + dx, cy + dy), q) for _, q in rooms):
                    best = (bx, by, b)
                    break
            if best:
                break
        bx, by, b = best or (X(cx), Y(cy), (X(cx) - wbox, Y(cy) - size, X(cx) + wbox, Y(cy) + 20))
        boxes.append(b)
        E.append(T(bx, by, name, size, "middle", "bold", "#222", halo=True))
        E.append(T(bx, by + 18, dims, 14, "middle", fill="#555", halo=True))
    # approximate overall dimensions
    if rooms:
        ax0 = min(v[0] for _, p in rooms for v in p); ax1 = max(v[0] for _, p in rooms for v in p)
        ay0 = min(v[1] for _, p in rooms for v in p); ay1 = max(v[1] for _, p in rooms for v in p)
        yc = Y(miny) + 34
        E.append(f'<g stroke="#444" stroke-width="1.5"><line x1="{X(ax0):.1f}" y1="{yc:.1f}" x2="{X(ax1):.1f}" y2="{yc:.1f}"/>'
                 f'<line x1="{X(ax0):.1f}" y1="{Y(ay0) + 6:.1f}" x2="{X(ax0):.1f}" y2="{yc + 8:.1f}"/>'
                 f'<line x1="{X(ax1):.1f}" y1="{Y(ay0) + 6:.1f}" x2="{X(ax1):.1f}" y2="{yc + 8:.1f}"/>'
                 f'<line x1="{X(ax0) - 6:.1f}" y1="{yc + 6:.1f}" x2="{X(ax0) + 6:.1f}" y2="{yc - 6:.1f}"/>'
                 f'<line x1="{X(ax1) - 6:.1f}" y1="{yc + 6:.1f}" x2="{X(ax1) + 6:.1f}" y2="{yc - 6:.1f}"/></g>')
        E.append(T((X(ax0) + X(ax1)) / 2, yc - 7, f"≈ {fmt(ax1 - ax0)} m", 17, "middle", halo=True))
        xc = X(minx) - 40
        E.append(f'<g stroke="#444" stroke-width="1.5"><line x1="{xc:.1f}" y1="{Y(ay0):.1f}" x2="{xc:.1f}" y2="{Y(ay1):.1f}"/>'
                 f'<line x1="{xc - 8:.1f}" y1="{Y(ay0):.1f}" x2="{X(ax0) - 6:.1f}" y2="{Y(ay0):.1f}"/>'
                 f'<line x1="{xc - 8:.1f}" y1="{Y(ay1):.1f}" x2="{X(ax0) - 6:.1f}" y2="{Y(ay1):.1f}"/>'
                 f'<line x1="{xc - 6:.1f}" y1="{Y(ay0) + 6:.1f}" x2="{xc + 6:.1f}" y2="{Y(ay0) - 6:.1f}"/>'
                 f'<line x1="{xc - 6:.1f}" y1="{Y(ay1) + 6:.1f}" x2="{xc + 6:.1f}" y2="{Y(ay1) - 6:.1f}"/></g>')
        ym = (Y(ay0) + Y(ay1)) / 2
        E.append(T(xc, ym + 6, f"≈ {fmt(ay1 - ay0)} m", 17, "middle", halo=True))
    # north (optional): north_deg = angle of north measured clockwise from the "top" of the drawing
    ng = num(d.get("north_deg"))
    if ng is not None:
        nx, ny = W - MR - 40, MT + 40
        a = math.radians(ng)                       # rotated by hand: not every renderer honours transform
        arrow = [rot_xy(u_, -v_, -a) for u_, v_ in ((0, -30), (-11, 14), (0, 6), (11, 14))]
        E.append('<polygon points="' + " ".join(f"{nx + u_:.1f},{ny - v_:.1f}" for u_, v_ in arrow) + '" fill="#222"/>')
        E.append(T(nx, ny + 38, tr("north"), 18, "middle", "bold"))

    # runs
    place = {o.get("id"): xy(o) for o in pts + tabs}
    tags, styles_used = [], set()
    for layer in (0, 1):
        for r in lst(d, "runs"):
            cid = r.get("circuit")
            if cid not in circ_ix or (layer == 0) == visible(cid) and only:
                continue
            if layer == 0 and not only:
                continue
            ci, c = circ_ix[cid]
            color, width, dash = circ_style(d, c, ci, mode)
            under = any(w in str(r.get("note", "")).lower() for w in UNDERGROUND_WORDS)
            if under:
                dash = "10 6"
            op = 1.0
            if not visible(cid):
                color, width, op = "#BDBDBD", 2.0, 0.7
            seq = [place.get(e) for e in (r.get("sequence") or []) if isinstance(e, str)]
            stretch = []
            for q in seq + [None]:
                if q is None:
                    if len(stretch) >= 2:
                        pp = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in stretch)
                        da = f' stroke-dasharray="{dash}"' if dash else ""
                        E.append(f'<polyline points="{pp}" fill="none" stroke="{color}" stroke-width="{width}" stroke-opacity="{op}"{da} '
                                 'stroke-linejoin="round" stroke-linecap="round"/>')
                        if visible(cid) and white_core(c, ci, mode):
                            E.append(f'<polyline points="{pp}" fill="none" stroke="#fff" stroke-width="{width * 0.4:.1f}"{da} '
                                     'stroke-linejoin="round" stroke-linecap="round"/>')
                        styles_used.add("under" if under else ("mbtf" if c.get("type") == "MBTF" else ""))
                        if visible(cid):
                            tags.append((cid, color, stretch, conductors(d, ix, c)))
                    stretch = []
                else:
                    stretch.append(q)
    # panels
    for t in tabs:
        x, y = xy(t)
        sym = "_ts" if t.get("upstream") else "_tp"
        E.append(symbol_svg(sym, X(x), Y(y), u * 1.1, "#111", 2.2, backdrop=False))
        E.append(T(X(x), Y(y) - 1.0 * u - 6, (t.get("id") or ""), 17, "middle", "bold", halo=True))
        boxes.append((X(x) - 30, Y(y) - 1.0 * u - 24, X(x) + 30, Y(y) - 1.0 * u))
    # points: dimmed ones first
    room_poly = {a.get("id"): p for a, p in rooms}
    order = sorted(pts, key=lambda p: visible(p.get("circuit")))
    labels = []
    for p in order:
        x, y = xy(p)
        cid = p.get("circuit")
        if cid in circ_ix:
            ci, c = circ_ix[cid]
            color = circ_style(d, c, ci, mode)[0]
        else:
            color = "#555"
        op = 1.0
        if not visible(cid):
            color, op = "#BDBDBD", 0.75
        ang = 0.0
        poly = room_poly.get(p.get("room"))
        if poly and (SYMBOLS.get(p.get("type")) or {}).get("orient"):
            dist, (wx, wy) = nearest_wall((x, y), poly)
            if dist < 1.2:
                ang = math.atan2(wx, -wy)
        E.append(symbol_svg(p.get("type"), X(x), Y(y), u, color, 2.4, ang, op))
        st = p.get("status")
        if st in ("fault", "doubtful") and visible(cid):
            bx, by = X(x) + 1.05 * u, Y(y) - 1.05 * u
            bc = "#C62828" if st == "fault" else "#B26A00"
            E.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="8.5" fill="{bc}" stroke="#fff" stroke-width="1.5"/>')
            E.append(T(bx, by + 5, "!" if st == "fault" else "?", 13, "middle", "bold", "#fff"))
        if visible(cid):
            labels.append((p, color))
    for p, color in labels:
        x, y = xy(p)
        Xp, Yp = X(x), Y(y)
        circ_txt = p.get("circuit") or ("" if p.get("type") in NO_CIRCUIT_OK else tr("no_circ"))
        txt = f"{p.get('id')}" + (f"·{circ_txt}" if circ_txt else "") + (f" {p['letter']}" if p.get("letter") else "")
        size = 14
        w = text_width(txt, size)
        cands = [(Xp + 1.5 * u, Yp - 1.0 * u, "start"), (Xp + 1.5 * u, Yp + 1.0 * u + size, "start"),
                 (Xp - 1.5 * u, Yp - 1.0 * u, "end"), (Xp - 1.5 * u, Yp + 1.0 * u + size, "end"),
                 (Xp, Yp - 1.6 * u, "middle"), (Xp, Yp + 1.6 * u + size, "middle"),
                 (Xp + 2.6 * u, Yp + 0.4 * u, "start"), (Xp - 2.6 * u, Yp + 0.4 * u, "end")]
        chosen = None
        for tx, ty, an in cands:
            x0 = tx if an == "start" else (tx - w if an == "end" else tx - w / 2)
            b = (x0, ty - size, x0 + w, ty + 3)
            if not collides(b, boxes):
                chosen = (tx, ty, an, b)
                break
        if not chosen:
            tx, ty, an = cands[0]
            chosen = (tx, ty, an, (tx, ty - size, tx + w, ty + 3))
        boxes.append(chosen[3])
        E.append(T(chosen[0], chosen[1], txt, size, chosen[2], "bold", color, halo=True))
    # circuit label on each long stretch (besides the color: works in black and white and for colour-blind readers)
    for cid, color, stretch, cond in tags:
        segs = sorted(((math.hypot(X(b[0]) - X(a[0]), Y(b[1]) - Y(a[1])), a, b) for a, b in zip(stretch, stretch[1:])), key=lambda z: -z[0])
        for k, (L, a, b) in enumerate(segs):
            if k > 0 and L < 300:
                break
            txt = f"{cid} {cond}" if k == 0 and cond else cid
            size = 13
            w = text_width(txt, size) + 8
            placed = False
            for t in (0.5, 0.35, 0.65, 0.25, 0.75):
                mx, my = X(a[0]) + (X(b[0]) - X(a[0])) * t, Y(a[1]) + (Y(b[1]) - Y(a[1])) * t
                bb = (mx - w / 2, my - 10, mx + w / 2, my + 9)
                if not collides(bb, boxes):
                    boxes.append(bb)
                    E.append(f'<rect x="{bb[0]:.1f}" y="{bb[1]:.1f}" width="{w:.1f}" height="19" rx="4" fill="#fff" stroke="{color}" stroke-width="1.5"/>')
                    E.append(T(mx, my + 4.5, txt, size, "middle", "bold", color))
                    placed = True
                    break
            if not placed and k == 0:
                continue

    # legend
    y0 = Y(miny) + 70
    E.append(f'<line x1="28" y1="{y0:.0f}" x2="{W - 28}" y2="{y0:.0f}" stroke="#222" stroke-width="2"/>')
    y = y0 + 36
    E.append(T(28, y, tr("legend"), 22, weight="bold"))
    used = []
    for p in pts:
        t = p.get("type") if p.get("type") in SYMBOLS else "_unknown"
        if t not in used:
            used.append(t)
    for t in tabs:
        k = "_ts" if t.get("upstream") else "_tp"
        if k not in used:
            used.append(k)
    cols = 3
    cw = (W - 56) / cols
    for i, t in enumerate(used):
        cx = 28 + (i % cols) * cw
        cy = y + 34 + (i // cols) * 40
        E.append(symbol_svg(t, cx + 24, cy - 6, 11, "#222", 2.2, backdrop=False))
        E.append(T(cx + 56, cy, cut(sym_name(t), 40), 17))
    y += 34 + ((len(used) + cols - 1) // cols) * 40
    marks = {p.get("status") for p in pts}
    extra = []
    if "fault" in marks:
        extra.append(("!", "#C62828", tr("mark.fault")))
    if "doubtful" in marks:
        extra.append(("?", "#B26A00", tr("mark.doubtful")))
    for i, (sgn, col, txt) in enumerate(extra):
        cx = 28 + i * cw
        E.append(f'<circle cx="{cx + 24}" cy="{y - 6}" r="9" fill="{col}"/>')
        E.append(T(cx + 24, y - 1, sgn, 14, "middle", "bold", "#fff"))
        E.append(T(cx + 56, y, txt, 17))
    if extra:
        y += 40
    E.append(T(28, y, tr("runs_note"), 15, fill="#444"))
    y += 26
    lines = []
    if "under" in styles_used:
        lines.append(("10 6", False, tr("line.under")))
    if "mbtf" in styles_used:
        lines.append(("12 4 2 4", False, tr("line.mbtf")))
    if mode == "circuit" and any(white_core(c, i, mode) for i, c in enumerate(lst(d, "circuits"))):
        lines.append(("", True, tr("line.core")))
    for da, hollow, txt in lines:
        dd = f' stroke-dasharray="{da}"' if da else ""
        E.append(f'<line x1="28" y1="{y - 5}" x2="74" y2="{y - 5}" stroke="#444" stroke-width="4"{dd}/>')
        if hollow:
            E.append(f'<line x1="28" y1="{y - 5}" x2="74" y2="{y - 5}" stroke="#fff" stroke-width="1.6"/>')
        E.append(T(84, y, txt, 15, fill="#444"))
        y += 24
    y += 8
    # circuits (or statuses)
    if mode == "status":
        E.append(T(28, y, tr("status_each"), 20, weight="bold"))
        y += 30
        count = {}
        for c in lst(d, "circuits"):
            count[(c.get("status") or "not_surveyed")] = count.get((c.get("status") or "not_surveyed"), 0) + 1
        for i, e in enumerate(STATUSES):
            cx = 28 + (i % 4) * ((W - 56) / 4)
            cy = y + (i // 4) * 32
            E.append(f'<line x1="{cx:.0f}" y1="{cy - 6}" x2="{cx + 46:.0f}" y2="{cy - 6}" stroke="{STATUS_COLOR[e]}" stroke-width="6"/>')
            E.append(T(cx + 56, cy, f"{st_txt(e)} ({count.get(e, 0)})", 16))
        y += 2 * 32 + 10
    present = []
    on_floor = {p.get("circuit") for p in pts} | {r.get("circuit") for r in lst(d, "runs")
                                                  if any(e in place for e in (r.get("sequence") or []) if isinstance(e, str))}
    for c in lst(d, "circuits"):
        if c.get("id") in on_floor and visible(c.get("id")):
            present.append(c)
    if only:
        present = [c for c in lst(d, "circuits") if c.get("id") in only]
    if present:
        E.append(T(28, y, tr("circ_sheet" if only else "circ_floor"), 20, weight="bold"))
        y += 30
        cols = 1 if only else 2
        cw = (W - 56) / cols
        nmax = int((cw - 70) / (15 * 0.58))
        for i, c in enumerate(present):
            ci = circ_ix[c.get("id")][0]
            color, width, dash = circ_style(d, c, ci, mode)
            cx = 28 + (i % cols) * cw
            cy = y + (i // cols) * 28
            da = f' stroke-dasharray="{dash}"' if dash else ""
            E.append(f'<line x1="{cx:.0f}" y1="{cy - 5}" x2="{cx + 50:.0f}" y2="{cy - 5}" stroke="{color}" stroke-width="{width + 1}"{da}/>')
            if white_core(c, ci, mode):
                E.append(f'<line x1="{cx:.0f}" y1="{cy - 5}" x2="{cx + 50:.0f}" y2="{cy - 5}" stroke="#fff" stroke-width="{(width + 1) * 0.4:.1f}"/>')
            dev = ix["devices"].get(c.get("device"))
            txt = (f"{c.get('id')} · {c.get('name') or ''} · {c.get('device') or '?'} {dev_label(dev).split(' ', 1)[-1] if dev else ''}"
                   f" · {fmt(num(c.get('section_mm2')))} mm² · {st_txt(c.get('status')) if c.get('status') else '?'}")
            if c.get("assigned_to"):
                txt += f" · {c['assigned_to']}"
            E.append(T(cx + 60, cy, cut(txt, nmax), 15, weight="bold" if only else "normal", fill="#111"))
        y += ((len(present) + cols - 1) // cols) * 28 + 10
    y += 10
    y += title_block(E, 28, y, W - 56, d, fname, tr("only", ids=", ".join(sorted(only))) if only else "") + 24
    return E, W, y


# ---------------------------------------------------------------- single-line diagram

SH = 92                                           # height of a device symbol in the single-line diagram [px]


def _dev_symbol(E, p, x, y, color="#111"):
    """Vertical device between y and y+SH (Anexo 771-K of AEA 90364-7-771 / IEC 60617). No rotated texts: not every renderer
    honours transform."""
    t = p.get("type")
    pol = num(p.get("poles"))
    n = int(pol) if pol else 0
    E.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y + 30}" stroke="{color}" stroke-width="2.5"/>')
    for k in range(min(n, 4)):                   # oblique ticks = number of conductors (poles)
        yy = y + 4 + k * 5
        E.append(f'<line x1="{x - 6}" y1="{yy + 4}" x2="{x + 6}" y2="{yy - 1}" stroke="{color}" stroke-width="1.6"/>')
    if not n:                                    # poles not surveyed: a "?" instead of ticks (do not draw double-pole what is unknown)
        E.append(f'<text x="{x + 5}" y="{y + 16}" font-size="13" font-weight="bold" fill="#c00" font-family="sans-serif">?</text>')
    if t == "FUSE":                              # fuse: rectangle crossed by the line
        E.append(f'<rect x="{x - 6}" y="{y + 32}" width="12" height="34" fill="#fff" stroke="{color}" stroke-width="2"/>')
        E.append(f'<line x1="{x}" y1="{y + 30}" x2="{x}" y2="{y + SH}" stroke="{color}" stroke-width="2.5"/>')
        return
    if t == "SPD":                               # surge protective device: non-linear element to earth
        E.append(f'<rect x="{x - 9}" y="{y + 32}" width="18" height="30" fill="#fff" stroke="{color}" stroke-width="2"/>')
        E.append(f'<polyline points="{x - 4},{y + 38} {x + 4},{y + 46} {x - 4},{y + 50} {x + 4},{y + 58}" fill="none" stroke="{color}" stroke-width="1.6"/>')
        E.append(f'<line x1="{x}" y1="{y + 62}" x2="{x}" y2="{y + 74}" stroke="{color}" stroke-width="2.5"/>')
        for k, w in enumerate((14, 9, 4)):
            E.append(f'<line x1="{x - w}" y1="{y + 74 + k * 5}" x2="{x + w}" y2="{y + 74 + k * 5}" stroke="{color}" stroke-width="2"/>')
        return
    E.append(f'<line x1="{x}" y1="{y + 66}" x2="{x - 18}" y2="{y + 33}" stroke="{color}" stroke-width="2.5"/>')   # open contact
    E.append(f'<line x1="{x}" y1="{y + 66}" x2="{x}" y2="{y + SH}" stroke="{color}" stroke-width="2.5"/>')
    if t in ("MCB", "RCBO", "MPCB"):             # circuit breaker: cross on the fixed contact (IEV 441-14-20)
        E.append(f'<line x1="{x - 5}" y1="{y + 25}" x2="{x + 5}" y2="{y + 35}" stroke="{color}" stroke-width="2.2"/>')
        E.append(f'<line x1="{x - 5}" y1="{y + 35}" x2="{x + 5}" y2="{y + 25}" stroke="{color}" stroke-width="2.2"/>')
    else:                                        # isolation: bar on the fixed contact (switch-disconnector, isolating RCD)
        E.append(f'<line x1="{x - 7}" y1="{y + 30}" x2="{x + 7}" y2="{y + 30}" stroke="{color}" stroke-width="2.5"/>')
    if t in ("RCD", "RCBO"):                     # RCD toroid and mechanical link
        E.append(f'<ellipse cx="{x}" cy="{y + 78}" rx="10" ry="5" fill="none" stroke="{color}" stroke-width="2"/>')
        E.append(f'<polyline points="{x + 10},{y + 78} {x + 17},{y + 78} {x + 17},{y + 50} {x - 8},{y + 50}" fill="none" stroke="{color}" '
                 'stroke-width="1.4" stroke-dasharray="3 3"/>')
    if t == "MPCB":
        E.append(f'<rect x="{x - 8}" y="{y + 70}" width="16" height="12" fill="#fff" stroke="{color}" stroke-width="1.6"/>')


def render_single_line(d, tabs_sel=None, W=WIDTH):
    """Tree from top to bottom. Final MCBs go in rows that wrap at the sheet width (each row with its bus bar), with horizontal
    texts: readable on a phone without rotating the image."""
    ix = indexes(d)
    circ_ix = {c.get("id"): (i, c) for i, c in enumerate(lst(d, "circuits"))}
    tabs = [t for t in lst(d, "panels") if not tabs_sel or t.get("id") in tabs_sel]
    CW, LEAF_H, GAP, OX = 172, 250, 30, 30
    E = []
    E.append(T(28, 48, cut(d.get("job") or tr("job"), 60), 32, weight="bold"))
    E.append(T(28, 84, tr("sl.title"), 20, fill="#333"))

    def children_of(pid, tid):
        hs = [("dev", p) for p in lst(d, "devices") if p.get("upstream") == pid and p.get("panel") == tid and p.get("id") != pid]
        hs += [("circ", c) for c in lst(d, "circuits") if c.get("device") == pid]
        hs += [("panel", t2) for t2 in lst(d, "panels") if t2.get("upstream") == pid]
        return hs

    def block(node, tid, avail, seen):
        """Returns (width, height, x_entry, draw(x, y))."""
        kind, o = node
        oid = o.get("id")
        if kind == "dev" and oid not in seen:
            hs = children_of(oid, tid)
            sub = [h for h in hs if h[0] == "dev" and h[1].get("id") not in seen]
            finals = [h for h in hs if h[0] != "dev"]
            if not sub:                          # final MCB: symbol + data + its circuit(s) below
                def draw(x, y, o=o, finals=finals):
                    xs = x + 26
                    _dev_symbol(E, o, xs, y)
                    E.append(T(xs + 24, y + 22, cut(oid, 14), 15, weight="bold"))
                    data = wrap(dev_label(o).split(" ", 1)[-1], 14)[:2]   # on two lines: a final RCD does not lose IΔn or class
                    for i, ln in enumerate(data):
                        E.append(T(xs + 24, y + 41 + i * 15, cut(ln, 14), 13))
                    lab = o.get("label") or ""
                    for i, ln in enumerate(wrap(f"«{lab}»", 16)[:3] if lab else []):
                        E.append(T(xs + 24, y + 59 + (len(data) - 1) * 15 + i * 16, ln, 12, fill="#444", italic=True))
                    yy = y + SH
                    for k, (kk, c) in enumerate(finals[:2]):
                        if kk == "circ":
                            ci, _ = circ_ix[c.get("id")]
                            color = PALETTE[ci % len(PALETTE)]
                            st = (c.get("status") or "not_surveyed")
                            E.append(f'<line x1="{xs}" y1="{yy}" x2="{xs}" y2="{yy + 26}" stroke="{color}" stroke-width="5"/>')
                            E.append(f'<polygon points="{xs - 7},{yy + 22} {xs + 7},{yy + 22} {xs},{yy + 34}" fill="{color}"/>')
                            ty = yy + 54
                            E.append(T(x + 8, ty, cut(c.get("id"), 18), 16, weight="bold", fill=color))
                            for i, ln in enumerate(wrap(c.get("name") or "", 21)[:2]):
                                E.append(T(x + 8, ty + 19 + i * 17, ln, 13))
                            s = num(c.get("section_mm2"))
                            E.append(T(x + 8, ty + 55, cut(f"{ct_txt(c.get('type'))} · {conductors(d, ix, c) or (fmt(s) + ' mm²' if s else tr('sl.section_unknown'))}", 22), 13, fill="#333"))
                            E.append(f'<rect x="{x + 8}" y="{ty + 63}" width="14" height="14" fill="{STATUS_COLOR.get(st, "#999")}" stroke="#222"/>')
                            E.append(T(x + 28, ty + 75, cut(st_txt(st), 20), 13,
                                       weight="bold", fill=STATUS_COLOR.get(st, "#333") if st != "not_surveyed" else "#555"))
                            if c.get("assigned_to"):
                                E.append(T(x + 28, ty + 92, cut(c["assigned_to"], 20), 13, weight="bold"))
                        else:
                            E.append(f'<line x1="{xs}" y1="{yy}" x2="{xs}" y2="{yy + 30}" stroke="#111" stroke-width="3"/>')
                            E.append(symbol_svg("_ts", xs, yy + 44, 9, "#111", 2, backdrop=False))
                            E.append(T(x + 8, yy + 76, tr("sl.to_panel", p=c.get("id")), 15, weight="bold"))
                    if len(finals) > 2:
                        E.append(T(x + 8, y + LEAF_H - 8, tr("sl.more", n=len(finals) - 2), 12, fill="#C62828"))
                    if not finals:
                        E.append(T(x + 8, yy + 30, tr("sl.no_circuit"), 13, fill="#777", italic=True))
                return CW, LEAF_H, 26, draw
            # device with devices below: rows that wrap at the available width
            subs = [block(h, tid, avail - 20, seen | {oid}) for h in sub]
            rows, row, width = [], [], 0
            for b in subs:
                if row and width + b[0] > avail:
                    rows.append(row)
                    row, width = [], 0
                row.append(b)
                width += b[0]
            if row:
                rows.append(row)
            if len(rows) == 1:
                ox = 0
                xa = (rows[0][0][2] + (sum(b[0] for b in rows[0][:-1]) + rows[0][-1][2])) / 2
            else:                                # several rows: the drop runs on the left, without covering the first column's texts
                ox, xa = OX, 12
            wmax = ox + max(sum(b[0] for b in f) for f in rows)
            height = SH + 30 + sum(max(b[1] for b in f) + GAP for f in rows) + (24 if finals else 0)
            total_w = max(wmax, xa + 300)

            def draw(x, y, o=o, rows=rows, xa=xa, finals=finals, ox=ox):
                X0 = x + xa
                _dev_symbol(E, o, X0, y)
                lines = [oid, dev_label(o)] + ([f"Icn {fmt(num(o.get('icn_ka')))} kA"] if num(o.get("icn_ka")) else []) + ([f"«{o['label']}»"] if o.get("label") else [])
                for i, ln in enumerate(lines[:4]):
                    E.append(T(X0 + 26, y + 22 + i * 19, cut(ln, 40), 17 if i == 0 else 15, weight="bold" if i == 0 else "normal", halo=True))
                yy = y + SH + 30
                last_bus = yy
                for f in rows:
                    hx, xx = [], x + ox
                    for b in f:
                        hx.append(xx + b[2])
                        xx += b[0]
                    E.append(f'<line x1="{min(hx + [X0]):.0f}" y1="{yy}" x2="{max(hx + [X0]):.0f}" y2="{yy}" stroke="#111" stroke-width="3"/>')
                    xx = x + ox
                    for b in f:
                        E.append(f'<line x1="{xx + b[2]:.0f}" y1="{yy}" x2="{xx + b[2]:.0f}" y2="{yy + 14}" stroke="#111" stroke-width="2.5"/>')
                        b[3](xx, yy + 14)
                        xx += b[0]
                    last_bus = yy
                    yy += max(b[1] for b in f) + GAP
                E.append(f'<line x1="{X0:.0f}" y1="{y + SH}" x2="{X0:.0f}" y2="{last_bus}" stroke="#111" stroke-width="2.5"/>')
                if finals:
                    E.append(T(X0 + 26, y + SH + 22, tr("sl.also_feeds") + ", ".join((f[1].get("id") or "") for f in finals), 13, fill="#C62828"))
            return total_w, height, xa, draw
        # loose node (cycle or missing device)
        def draw(x, y, o=o):
            E.append(T(x + 8, y + 30, tr("sl.cycle", o=oid), 13, fill="#C62828"))
        return CW, 60, 26, draw

    y = 112
    sup = d.get("supply") if isinstance(d.get("supply"), dict) else {}
    three = sup.get("type") == "three_phase"
    for t in tabs:
        tid = t.get("id")
        devs = [p for p in lst(d, "devices") if p.get("panel") == tid]
        ids = {p.get("id") for p in devs}
        roots = [("dev", p) for p in devs if p.get("upstream") not in ids or p.get("upstream") == p.get("id")]
        reached = set()

        def mark(pid):
            stack = [pid]
            while stack:
                q = stack.pop()
                if q in reached:
                    continue
                reached.add(q)
                stack += [x.get("id") for x in devs if x.get("upstream") == q]
        for _, r in roots:
            mark(r.get("id"))
        for p in devs:                            # devices in a cycle (A hangs from B and B from A): without this they were not drawn
            if p.get("id") not in reached:
                roots.append(("dev", p))
                mark(p.get("id"))
        avail = W - 120
        bs = [block(r, tid, avail, frozenset()) for r in roots]
        # independent incomers (e.g. one per apartment in the meter cabinet): side by side, in rows at the sheet width
        rows_r, row_r, width_r = [], [], 0
        for b in bs:
            if row_r and width_r + b[0] > avail:
                rows_r.append(row_r)
                row_r, width_r = [], 0
            row_r.append(b)
            width_r += b[0]
        if row_r:
            rows_r.append(row_r)
        loose = [c for c in lst(d, "circuits") if c.get("device") not in ix["devices"]] if t is tabs[0] else []
        height = sum(max(b[1] for b in f) + GAP for f in rows_r) + (40 if loose else 0)
        E.append(f'<rect x="30" y="{y:.0f}" width="{W - 60:.0f}" height="{height + 80:.0f}" fill="none" stroke="#666" stroke-width="1.5" stroke-dasharray="8 5"/>')
        E.append(T(46, y + 30, f"{tid} — {t.get('name') or tr('panel')}", 22, weight="bold"))
        if t.get("upstream"):
            q = ix["devices"].get(t["upstream"])
            feed = tr("sl.fed_from", u=t["upstream"]) + (tr("sl.fed_in", p=q.get("panel")) if q else "")
        else:
            feed = tr("sl.utility", s=tr("sl.three" if three else "sl.single"), t=tid)
        E.append(T(46, y + 56, feed, 16, fill="#444"))
        yy = y + 90
        for f in rows_r:
            xx = 60
            for b in f:
                E.append(f'<line x1="{xx + b[2]:.0f}" y1="{yy - 22}" x2="{xx + b[2]:.0f}" y2="{yy}" stroke="#111" stroke-width="3"/>')
                b[3](xx, yy)
                xx += b[0]
            yy += max(b[1] for b in f) + GAP
        if loose:
            E.append(T(60, yy + 10, tr("sl.no_device") + ", ".join((c.get("id") or "") for c in loose), 15, weight="bold", fill="#C62828"))
        y += height + 120
    E.append(T(28, y, tr("legend"), 22, weight="bold"))
    y += 18
    examples = [(k, tr("sl.ex." + k)) for k in DEVICE_TYPES]
    used = {p.get("type") for p in lst(d, "devices")}
    examples = [e for e in examples if e[0] in used] or examples[:2]
    cw = (W - 56) / 3
    for i, (tp, txt) in enumerate(examples):
        cx = 28 + (i % 3) * cw + 20
        cy = y + (i // 3) * 115
        _dev_symbol(E, {"type": tp, "poles": 2}, cx, cy)
        E.append(T(cx + 36, cy + 54, txt, 16))
    y += ((len(examples) + 2) // 3) * 115 + 14
    E.append(T(28, y, tr("sl.ticks"), 15, fill="#444"))
    y += 30
    for i, e in enumerate(STATUSES):
        cx = 28 + (i % 4) * ((W - 56) / 4)
        cy = y + (i // 4) * 30
        E.append(f'<rect x="{cx:.0f}" y="{cy - 15}" width="18" height="18" fill="{STATUS_COLOR[e]}" stroke="#222"/>')
        E.append(T(cx + 28, cy, st_txt(e), 16))
    y += 70
    for ln in wrap(tr("sl.symbols"), 150):
        E.append(T(28, y, ln, 14, fill="#444"))
        y += 20
    y += 10
    y += title_block(E, 28, y, W - 56, d, tr("sl.panels", p=", ".join((t.get("id") or "") for t in tabs))) + 24
    return E, W, y


# ---------------------------------------------------------------- work sheets

def sheet_content(d, c, survey_ref, lang=None):
    """Everything a work sheet says about circuit c, in the current language (or lang)."""
    if lang:
        use_lang(lang)
    ix = indexes(d)
    cid = c.get("id")
    dev = ix["devices"].get(c.get("device"))
    ch = chain(ix, c.get("device"), d)
    tab = ix["panels"].get(dev.get("panel")) if dev else None
    head = [q for q in ch[1:]]
    pts = points_of(d, cid)
    meds = [m for m in c.get("measurements", []) if isinstance(m, dict)] if isinstance(c.get("measurements"), list) else []
    done = {m.get("type") for m in meds if m.get("ok") is True}
    pend = []
    if "insulation" not in done:
        pend.append(tr("sh.pend.insulation"))
    if "pe_continuity" not in done and any(p.get("type") not in SWITCHES for p in pts):
        pend.append(tr("sh.pend.pe"))
    if "rcd_trip" not in done and c.get("status") in ("repaired", "under_repair", "fault", "measured"):
        pend.append(tr("sh.pend.rcd"))
    others = [o for o in lst(d, "circuits") if o.get("status") == "under_repair" and o.get("id") != cid and o.get("assigned_to")]
    poles = int(num(dev.get("poles")) or 2) if dev else 0
    lock = (tr("sh.lock", d=dev.get("id"), l=dev.get("label") or tr("sh.no_label"), t=dev_label(dev), p=tab.get("id") if tab else "?",
               n=tab.get("name") if tab else "")) if dev else tr("sh.no_device")
    headtxt = " → ".join(f"{q.get('id')} ({dev_label(q)})" for q in head) or tr("sh.none_entered")
    check = [
        tr("ck.1", d=dev.get("id") if dev else "?", g=head[-1].get("id") if head else tr("sh.main")),
        tr("ck.2"),
        tr("ck.3", x=tr("ck.3x") if poles >= 3 else ""),
        tr("ck.4"),
        tr("ck.5"),
        tr("ck.6"),
        tr("ck.7"),
    ]
    no_poles = bool(dev) and not num(dev.get("poles"))
    if poles == 1 or no_poles or c.get("type") == "OTHER" or any(w in str(x).lower() for x in (c.get("notes"), c.get("name")) for w in NEUTRAL_WORDS):
        check.insert(2, tr("ck.neutral", x=tr("ck.neutral_x") if no_poles else ""))
    return {"cid": cid, "name": c.get("name") or "", "status": (c.get("status") or "not_surveyed"), "assigned_to": c.get("assigned_to") or tr("sh.unassigned"),
            "lock": lock, "upstream": headtxt, "points": pts, "measurements": meds, "pending": pend, "checklist": check,
            "others": [f"{o.get('id')} ({o.get('name') or ''}): {o.get('assigned_to')}" for o in others], "notes": c.get("notes") or "",
            "status_cmd": f"gateway electricidad plan status {shlex.quote(survey_ref)} {shlex.quote(str(cid))} repaired --tech \"{tr('sh.name')}\" --note \"...\""}


def meas_line(m):
    ok = tr("sh.ok") if m.get("ok") else tr("sh.bad") if m.get("ok") is False else "?"
    return f"{m.get('date', '?')} {mt_txt(m.get('type'))}: {fmt(num(m.get('value')), 2)} {m.get('unit') or ''} {ok}"


def render_sheet(d, c, survey_ref):
    h = sheet_content(d, c, survey_ref)
    ix = indexes(d)
    pts = h["points"]
    floors = [p.get("floor") for p in pts if p.get("floor")] or [next(iter(ix["floors"]), "PB")]
    floor = max(set(floors), key=floors.count)
    E, W, y = render_plan(d, floor, "circuit", only=[h["cid"]], title=tr("sh.title", c=h["cid"], n=h["name"], a=h["assigned_to"]))
    y -= 10
    E.append(f'<line x1="28" y1="{y}" x2="{W - 28}" y2="{y}" stroke="#222" stroke-width="2"/>')
    y += 44
    E.append(f'<rect x="28" y="{y - 30}" width="{W - 56}" height="96" fill="#FFF3E0" stroke="#E65100" stroke-width="3"/>')
    E.append(T(44, y, tr("sh.lockout"), 22, weight="bold", fill="#B71C1C"))
    E.append(T(44, y + 28, cut(h["lock"], 120), 18, weight="bold"))
    E.append(T(44, y + 54, cut(tr("sh.upstream", u=h["upstream"]), 130), 16))
    y += 100
    E.append(T(28, y, tr("sh.points", c=h["cid"], n=len(pts)), 20, weight="bold"))
    y += 12
    colw = [110, 220, 280, 110, 150, W - 56 - 870]
    heads = tr("sh.heads")
    rows = [[(p.get("id") or ""), sym_name(p.get("type")) if p.get("type") in SYMBOLS else str(p.get("type") or ""),
             (ix["rooms"].get(p.get("room")) or {}).get("name") or p.get("room") or "",
             (fmt(num(p.get("height_m")), 2) + " m") if num(p.get("height_m")) is not None else "", pst_txt(p.get("status") or "unverified"),
             p.get("note") or ""] for p in pts] or [["—", tr("sh.no_points"), "", "", "", ""]]
    for r_i, r in enumerate([heads] + rows):
        x = 28
        yy = y + r_i * 30
        if r_i == 0:
            E.append(f'<rect x="28" y="{yy}" width="{W - 56}" height="30" fill="#EEE"/>')
        E.append(f'<line x1="28" y1="{yy + 30}" x2="{W - 28}" y2="{yy + 30}" stroke="#BBB"/>')
        for k, cell in enumerate(r):
            col = "#C62828" if (k == 4 and r_i > 0 and pts and pts[r_i - 1].get("status") == "fault") else "#111"
            E.append(T(x + 6, yy + 21, cut(cell, int(colw[k] / 9)), 15, weight="bold" if r_i == 0 or k == 0 else "normal", fill=col))
            x += colw[k]
    y += (len(rows) + 1) * 30 + 34

    def section(title, items, check=False, color="#111"):
        nonlocal y
        E.append(T(28, y, title, 20, weight="bold", fill=color))
        y += 30
        for it in items:
            lines = wrap(it, 150)
            if check:
                E.append(f'<rect x="32" y="{y - 15}" width="16" height="16" fill="#fff" stroke="#222" stroke-width="1.6"/>')
            for ln in lines:
                E.append(T(60 if check else 40, y, ("" if check else "• ") + ln if ln is lines[0] else ln, 16))
                y += 23
            y += 4
        y += 14
    section(tr("sh.meas"), [meas_line(m) for m in h["measurements"]] or [tr("sh.none_yet")])
    section(tr("sh.pending"), h["pending"] or [tr("sh.none")])
    section(tr("sh.checklist"), h["checklist"], check=True, color="#B71C1C")
    if h["others"]:
        section(tr("sh.others"), h["others"])
    if h["notes"]:
        section(tr("sh.notes"), [h["notes"]])
    section(tr("sh.tell"), [h["status_cmd"]])
    return E, W, y + 10, h


def sheet_md(d, h, img):
    heads = tr("sh.heads")
    out = [tr("md.title", c=h["cid"], n=h["name"]), "",
           tr("md.info", j=d.get("job", ""), s=st_txt(h["status"]), a=h["assigned_to"], d=d.get("date", "?")),
           "", f"![{tr('md.img', c=h['cid'])}]({img})", "", tr("md.lockout"), "", f"**{h['lock']}**", "",
           tr("sh.upstream", u=h["upstream"]), "", tr("md.points", n=len(h["points"])), "",
           "| " + " | ".join(heads) + " |", "|" + "---|" * len(heads)]
    ix = indexes(d)
    for p in h["points"]:
        room = (ix["rooms"].get(p.get("room")) or {}).get("name") or p.get("room") or ""
        hgt = (fmt(num(p.get("height_m")), 2) + " m") if num(p.get("height_m")) is not None else ""
        kind = sym_name(p.get("type")) if p.get("type") in SYMBOLS else str(p.get("type") or "")
        cells = [(p.get("id") or ""), kind, room, hgt, pst_txt(p.get("status") or "unverified"), p.get("note") or ""]
        out.append("| " + " | ".join(str(x).replace("|", "/") for x in cells) + " |")
    out += ["", tr("md.meas"), ""]
    out += [f"- {meas_line(m)}" for m in h["measurements"]] or ["- " + tr("md.none_entered")]
    out += ["", tr("md.pending"), ""] + [f"- {x}" for x in h["pending"] or [tr("sh.none")]]
    out += ["", tr("md.checklist"), ""] + [f"- [ ] {x}" for x in h["checklist"]]
    if h["others"]:
        out += ["", tr("md.others"), ""] + [f"- {x}" for x in h["others"]]
    if h["notes"]:
        out += ["", tr("md.notes"), "", h["notes"]]
    out += ["", tr("md.finish"), "", f"`{h['status_cmd']}`", "", f"_{tr('footer')}. {tr('md.not_proof')}_", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- conversion to PNG / PDF

def convert(svgs, fmt_, dest):
    """svgs: list of .svg paths. fmt_ png: one PNG per SVG; pdf: a single (multi-page) PDF at dest. Returns (paths, warnings)."""
    if fmt_ == "svg" or not svgs:
        return [], []
    warnings = []
    tools = [h for h in ("typst", "rsvg-convert", "magick", "convert", "inkscape") if shutil.which(h)]
    if not tools:
        return [], [f"No typst, rsvg-convert, ImageMagick or inkscape on this machine: only the SVGs remain ({fmt_.upper()} skipped)."]

    def run(cmd, cwd=None):
        try:
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=180)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def svg_width(p):
        try:
            m = re.search(r'width="(\d+(?:\.\d+)?)"', open(p, encoding="utf-8").read(2000))
            return float(m.group(1)) if m else WIDTH
        except OSError:
            return WIDTH
    outputs = []
    jobs = [(s, os.path.splitext(s)[0] + ".png") for s in svgs] if fmt_ == "png" else [(svgs, dest)]
    for src, out in jobs:
        done = False
        items = src if isinstance(src, list) else [src]
        for h in tools:
            if os.path.exists(out):
                os.unlink(out)
            if h == "typst":
                base = os.path.dirname(os.path.abspath(items[0]))
                fd, typ = tempfile.mkstemp(suffix=".typ", dir=base)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write("#set page(width: auto, height: auto, margin: 5mm)\n")
                    f.write("\n#pagebreak()\n".join(f'#image("{os.path.basename(s)}", width: {svg_width(s) * 0.75:.0f}pt)' for s in items) + "\n")
                cmd = ["typst", "compile", typ, os.path.abspath(out)] + (["--ppi", f"{round(96 * WIDTH / svg_width(items[0]))}"] if fmt_ == "png" else [])
                done = run(cmd, cwd=base)
                os.unlink(typ)
            elif h == "rsvg-convert":
                done = run(["rsvg-convert", "-f", fmt_, "-b", "white", "-o", out] + items)
            elif h in ("magick", "convert"):
                done = run([h, "-density", "96", "-background", "white"] + items + (["-flatten", "-depth", "8"] if fmt_ == "png" else []) + [out])
            elif h == "inkscape" and len(items) == 1:
                done = run(["inkscape", items[0], f"--export-type={fmt_}", f"--export-filename={out}", "--export-background=white"])
            if done and os.path.exists(out) and os.path.getsize(out) > 0:
                outputs.append(out)
                break
            done = False
        if not done:
            warnings.append(f"Could not convert {os.path.basename(items[0])} to {fmt_.upper()} with {', '.join(tools)}: the SVG remains.")
    return outputs, warnings


# ---------------------------------------------------------------- DXF R12 ASCII (by hand, no libraries)

ACI = [1, 3, 5, 6, 4, 30, 140, 200, 40, 210, 92, 50, 160, 240, 8]


def dxf_txt(s, enc="cp1252"):
    # no line breaks or control characters (they would break the code/value pairs), "^" escaped (in DXF "^X" is a control
    # character), at most 250 characters (R12 string limit) and in the declared code page; a letter the code page lacks loses its
    # accent (é → e) before falling back to "?"
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(s)).replace("^", "^ ")[:250]
    out = []
    for ch in s:
        try:
            ch.encode(enc)
            out.append(ch)
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", ch).encode(enc, "ignore").decode(enc)
            out.append(base or "?")
    return "".join(out)


def layer(name):
    return re.sub(r"[^A-Z0-9_$-]", "_", name.upper())[:31]


def dxf_floor(d, floor_id):
    ix = indexes(d)
    enc, codepage = DXF_CODEPAGE[_LANG[0]]
    circ_ix = {c.get("id"): (i, c) for i, c in enumerate(lst(d, "circuits"))}
    rooms = [(a, polygon(a)) for a in lst(d, "rooms") if a.get("floor") == floor_id]
    rooms = [(a, p) for a, p in rooms if p]
    pts = [p for p in lst(d, "points") if p.get("floor") == floor_id and xy(p)]
    tabs = [t for t in lst(d, "panels") if t.get("floor") == floor_id and xy(t)]
    layers = [("0", 7), ("ROOMS", 7), ("DIMENSIONS", 8), ("PANELS", 1), ("TEXT", 7), ("NO_CIRCUIT", 9)]
    circ_layers, used = {}, {n for n, _ in layers}
    for cid, (i, c) in circ_ix.items():
        if not cid:
            continue
        n, k = layer(f"CIRC_{cid}"), 2
        while n in used:                          # "C 1" and "C-1" give the same layer: the second gets a suffix (no repeated layers)
            n, k = layer(f"CIRC_{cid}")[:27] + f"_{k}", k + 1
        used.add(n)
        circ_layers[cid] = n
        layers.append((n, ACI[i % len(ACI)]))
    ent = []

    def g(*pairs):
        for code, val in pairs:
            if isinstance(val, float):
                val = f"{val:.4f}"
            ent.append(f"{code:>3}\n{val}")

    def line(ly, x1, y1, x2, y2):
        g((0, "LINE"), (8, ly), (10, float(x1)), (20, float(y1)), (30, 0.0), (11, float(x2)), (21, float(y2)), (31, 0.0))

    def poly(ly, pts_, closed=False):
        g((0, "POLYLINE"), (8, ly), (66, 1), (10, 0.0), (20, 0.0), (30, 0.0), (70, 1 if closed else 0))
        for x, y in pts_:
            g((0, "VERTEX"), (8, ly), (10, float(x)), (20, float(y)), (30, 0.0))
        g((0, "SEQEND"), (8, ly))

    def circle(ly, x, y, r):
        g((0, "CIRCLE"), (8, ly), (10, float(x)), (20, float(y)), (30, 0.0), (40, float(r)))

    def text(ly, x, y, s, h, centre=False):
        if centre:
            g((0, "TEXT"), (8, ly), (10, float(x)), (20, float(y)), (30, 0.0), (40, float(h)), (1, dxf_txt(s, enc)), (72, 1), (11, float(x)), (21, float(y)), (31, 0.0), (73, 2))
        else:
            g((0, "TEXT"), (8, ly), (10, float(x)), (20, float(y)), (30, 0.0), (40, float(h)), (1, dxf_txt(s, enc)))

    def symbol(ly, kind, x, y, u, ang):
        sym = SYMBOLS.get(kind) or SYMBOLS["_unknown"]
        if not sym.get("orient"):
            ang = 0.0
        for pr in sym["prims"]:
            if pr[0] == "c":
                cx, cy = rot_xy(pr[1], pr[2], ang)
                circle(ly, x + cx * u, y + cy * u, pr[3] * u)
            elif pr[0] == "t":
                tx, ty = rot_xy(pr[1], pr[2], ang)
                text(ly, x + tx * u, y + ty * u, pr[3], pr[4] * u, centre=True)
            else:
                poly(ly, [(x + a * u, y + b * u) for a, b in prim_points(pr, ang)])
    xs, ys = [], []
    for a, p in rooms:
        poly("ROOMS", p, True)
        cx, cy = centroid(p)
        bw, bh = max(v[0] for v in p) - min(v[0] for v in p), max(v[1] for v in p) - min(v[1] for v in p)
        text("TEXT", cx, cy + 0.12, a.get("name") or a.get("id"), 0.22, True)
        text("DIMENSIONS", cx, cy - 0.22, tr("dxf.approx", w=fmt(bw), h=fmt(bh)), 0.14, True)
        xs += [v[0] for v in p]
        ys += [v[1] for v in p]
    for t in tabs:
        x, y = xy(t)
        symbol("PANELS", "_ts" if t.get("upstream") else "_tp", x, y, 0.15, 0)
        text("PANELS", x, y + 0.3, (t.get("id") or ""), 0.18, True)
    place = {o.get("id"): xy(o) for o in pts + tabs}
    for r in lst(d, "runs"):
        ly = circ_layers.get(r.get("circuit"), "NO_CIRCUIT")
        seq = [place[e] for e in (r.get("sequence") or []) if isinstance(e, str) and e in place]
        if len(seq) >= 2:
            poly(ly, seq)
    room_poly = {a.get("id"): p for a, p in rooms}
    for p in pts:
        x, y = xy(p)
        ly = circ_layers.get(p.get("circuit"), "NO_CIRCUIT")
        ang = 0.0
        poly_ = room_poly.get(p.get("room"))
        if poly_ and (SYMBOLS.get(p.get("type")) or {}).get("orient"):
            dist, (wx, wy) = nearest_wall((x, y), poly_)
            if dist < 1.2:
                ang = math.atan2(wx, -wy)
        symbol(ly, p.get("type"), x, y, 0.15, ang)
        text(ly, x + 0.22, y + 0.18, f"{p.get('id')} {p.get('circuit') or ''}".strip() + (f" {p['letter']}" if p.get("letter") else ""), 0.1)
        xs.append(x)
        ys.append(y)
    if rooms:                                     # overall dimension: rooms only (it used to include the 0,0 origin and the points)
        ax0 = min(v[0] for _, p in rooms for v in p)
        ax1 = max(v[0] for _, p in rooms for v in p)
        ay0 = min(v[1] for _, p in rooms for v in p)
        line("DIMENSIONS", ax0, ay0 - 0.8, ax1, ay0 - 0.8)
        line("DIMENSIONS", ax0, ay0 - 0.6, ax0, ay0 - 1.0)
        line("DIMENSIONS", ax1, ay0 - 0.6, ax1, ay0 - 1.0)
        text("DIMENSIONS", (ax0 + ax1) / 2, ay0 - 0.65, tr("dxf.approx1", w=fmt(ax1 - ax0)), 0.18, True)
    floor = ix["floors"].get(floor_id, {})
    xs += [xy(t)[0] for t in tabs]
    ys += [xy(t)[1] for t in tabs]
    if not xs:
        xs, ys = [0.0], [0.0]
    yb = min(ys) - 1.6
    source = str(d.get("source", ""))
    for i, s in enumerate([d.get("job", ""), tr("dxf.floor", f=floor.get("name") or floor_id), tr("dxf.date", d=d.get("date", "?"), s=source),
                           tr("dxf.sketch") if is_sketch(d) else tr("dxf.meters"), tr("dxf.layers"), tr("footer")]):
        text("TEXT", min(xs), yb - i * 0.32, s, 0.2 if i == 0 else 0.14)
    ys.append(yb - 6 * 0.32)
    hdr = ["  0\nSECTION", "  2\nHEADER", "  9\n$ACADVER", "  1\nAC1009", "  9\n$DWGCODEPAGE", f"  3\n{codepage}",
           "  9\n$INSBASE", " 10\n0.0", " 20\n0.0", " 30\n0.0",
           "  9\n$EXTMIN", f" 10\n{min(xs) - 1:.4f}", f" 20\n{min(ys) - 1:.4f}", " 30\n0.0",
           "  9\n$EXTMAX", f" 10\n{max(xs) + 1:.4f}", f" 20\n{max(ys) + 1:.4f}", " 30\n0.0", "  0\nENDSEC"]
    tables = ["  0\nSECTION", "  2\nTABLES",
              "  0\nTABLE", "  2\nLTYPE", " 70\n1", "  0\nLTYPE", "  2\nCONTINUOUS", " 70\n0", "  3\nSolid line", " 72\n65", " 73\n0", " 40\n0.0", "  0\nENDTAB",
              "  0\nTABLE", "  2\nLAYER", f" 70\n{len(layers)}"]
    for n, col in layers:
        tables += ["  0\nLAYER", f"  2\n{n}", " 70\n0", f" 62\n{col}", "  6\nCONTINUOUS"]
    tables += ["  0\nENDTAB", "  0\nTABLE", "  2\nSTYLE", " 70\n1", "  0\nSTYLE", "  2\nSTANDARD", " 70\n0", " 40\n0.0", " 41\n1.0", " 50\n0.0",
               " 71\n0", " 42\n0.2", "  3\ntxt", "  4\n", "  0\nENDTAB", "  0\nENDSEC"]
    blocks = ["  0\nSECTION", "  2\nBLOCKS", "  0\nENDSEC"]
    body = ["  0\nSECTION", "  2\nENTITIES"] + ent + ["  0\nENDSEC", "  0\nEOF"]
    return "\n".join(hdr + tables + blocks + body) + "\n", [n for n, _ in layers]


# ---------------------------------------------------------------- commands

def parse(argv, spec):
    out, pos, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            out["json"] = True
            i += 1
            continue
        if a.startswith("--"):
            if a not in spec:
                raise Usage(f"Unknown option \"{a}\". Options: {', '.join(sorted(spec)) or 'none'}, --json.")
            if i + 1 >= len(argv):
                raise Usage(f"Missing value for {a}.")
            v = argv[i + 1]
            if spec[a] and v not in spec[a]:
                raise Usage(f"{a} accepts {' | '.join(spec[a])} (got \"{v}\").")
            out[a[2:]] = v
            i += 2
            continue
        pos.append(a)
        i += 1
    return out, pos


def short_name(path):
    """The job name if the file is ROOT/JOB/survey.json (the command line accepts it that way); otherwise the full path."""
    ap = os.path.abspath(path)
    job = os.path.basename(os.path.dirname(ap))
    return job if ap == os.path.join(os.path.abspath(ROOT), job, SURVEY) else ap


def out_dir(path, opts):
    """Output folder: job/output, or --out, which must stay INSIDE the job folder (relative to it if not absolute). Checked with
    realpath before and after creating it, so neither ".." nor a symlink takes it outside."""
    job = os.path.dirname(os.path.abspath(path))
    asked = opts.get("out")
    out = os.path.join(job, OUT_DIR) if not asked else os.path.join(job, os.path.expanduser(asked))
    real_job = os.path.realpath(job)

    def in_job(p):
        r = os.path.realpath(p)
        return os.path.commonpath([real_job, r]) == real_job
    if not in_job(out):
        raise Usage(f"--out must stay inside the job folder ({job}); got \"{asked}\".")
    os.makedirs(out, exist_ok=True)
    if not in_job(out) or not os.path.isdir(out):
        raise Usage(f"--out \"{asked}\" points outside the job folder.")
    return os.path.abspath(out)


def free_name(name, used):
    """Two different ids can give the same file name ("C 1" and "C-1"): the second gets a suffix, it does not overwrite the first."""
    base, ext = os.path.splitext(name)
    n, k = name, 2
    while n.lower() in used:
        n, k = f"{base}_{k}{ext}", k + 1
    used.add(n.lower())
    return n


@contextlib.contextmanager
def lock(path):
    """Exclusive inter-process lock to read-modify-write the survey (two technicians reporting progress at once)."""
    if fcntl is None:
        yield
        return
    fd = os.open(os.path.join(os.path.dirname(os.path.abspath(path)), "." + os.path.basename(path) + ".lock"), os.O_RDWR | os.O_CREAT, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def write(path, text):
    write_atomic(path, text)
    return path


def report(opts, files, warnings, extra=None):
    if opts.get("json"):
        r = {"files": files, "warnings": warnings}
        r.update(extra or {})
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        for a in files:
            print(f"📄 {a}")
        for a in warnings:
            print(f"⚠️ {a}")
    return 0


def validation_warnings(d):
    F = validate(d)
    nf = sum(1 for f in F if f["status"] == "fail")
    return [f"The survey has {nf} error(s): run \"validate\" before handing out sheets (ELEC-PLA-18)."] if nf else []


LANG_OPT = {"--lang": LANGS}
FORMATS = ("svg", "png", "pdf")


def cmd_new(argv):
    opts, pos = parse(argv, {"--dir": None, **LANG_OPT})
    if len(pos) != 1:
        raise Usage("Usage: electricidad-plan new JOB [--dir DIR] [--lang es|ru|en]")
    use_lang(pick_lang(opts.get("lang")))
    job = slug(pos[0].lower())
    base = opts.get("dir") or ROOT
    path = os.path.join(base, job, SURVEY)
    if os.path.exists(path):
        raise Usage(f"{path} already exists: not overwriting it. Use another name or edit that one.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d = {"version": VERSION, "job": pos[0].strip()[:80], "source": "by-eye sketch", "date": datetime.date.today().isoformat(),
         "supply": {"type": "single_phase", "voltage_v": 220}, "floors": [{"id": "PB", "name": tr("new.floor")}],
         "rooms": [], "panels": [{"id": "TP", "name": tr("new.panel"), "floor": "PB", "x": 0.2, "y": 0.2, "upstream": None}],
         "devices": [], "circuits": [], "points": [], "runs": []}
    write_atomic(path, json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    return report(opts, [path], [], {"job": job})


def cmd_validate(argv):
    opts, pos = parse(argv, {})
    if len(pos) != 1:
        raise Usage("Usage: electricidad-plan validate F [--json]")
    d, path = load(pos[0])
    F = validate(d)
    nf = sum(1 for f in F if f["status"] == "fail")
    nw = sum(1 for f in F if f["status"] == "warn")
    if opts.get("json"):
        print(json.dumps({"file": path, "errors": nf, "warnings": nw, "findings": F, "as_of": AS_OF}, ensure_ascii=False, indent=1))
    else:
        c = {k: len(lst(d, k)) for k in ("rooms", "panels", "devices", "circuits", "points")}
        print(f"{path}: {c['rooms']} rooms, {c['panels']} panels, {c['devices']} devices, {c['circuits']} circuits, {c['points']} points")
        for f in F:
            print(f"{STATUS_MARK[f['status']]} [{f['rule']}] {f['evidence']}")
        print(f"{nf} error(s), {nw} warning(s)." + (" No errors." if not nf else " Fix the errors before drawing and handing out sheets (ELEC-PLA-18)."))
    return 1 if nf else 0


def cmd_draw(argv):
    opts, pos = parse(argv, {"--floor": None, "--color": ("circuit", "status"), "--only": None, "--format": FORMATS, "--out": None, **LANG_OPT})
    if len(pos) != 1:
        raise Usage("Usage: electricidad-plan draw F [--floor PB] [--color circuit|status] [--only C1,C2] [--format svg|png|pdf] [--out DIR] [--lang es|ru|en]")
    use_lang(pick_lang(opts.get("lang")))
    raw, path = load(pos[0])
    d = sanitize(raw)[0]
    mode = opts.get("color", "circuit")
    only = [s.strip() for s in opts.get("only", "").split(",") if s.strip()]
    ix = indexes(d)
    bad = [s for s in only if s not in ix["circuits"]]
    if bad:
        raise Usage(f"No circuit(s) {', '.join(bad)}. Circuits: {', '.join(ix['circuits']) or 'none'}.")
    if not floors_of(d):
        raise Usage("The survey has no floors: add at least {\"id\": \"PB\"}.")
    out = out_dir(path, opts)
    svgs = []
    for floor in floors_of(d, opts.get("floor")):
        if only and not any(p.get("floor") == floor and p.get("circuit") in only for p in lst(d, "points")) and not opts.get("floor") and len(floors_of(d)) > 1:
            continue
        E, W, H = render_plan(d, floor, mode, only)
        name = f"plan_{slug(floor)}_{mode}" + (f"_only-{slug('-'.join(only), 40)}" if only else "") + ".svg"
        svgs.append(write(os.path.join(out, name), svg_doc(E, W, H, f"{d.get('job', '')} — {floor}")))
    fmt_ = opts.get("format", "png")
    if fmt_ == "pdf":
        conv, av = convert(svgs, "pdf", os.path.splitext(svgs[0])[0] + ".pdf") if svgs else ([], [])
    else:
        conv, av = convert(svgs, fmt_, None)
    return report(opts, svgs + conv, validation_warnings(raw) + av)


def cmd_single_line(argv):
    opts, pos = parse(argv, {"--panel": None, "--format": FORMATS, "--out": None, **LANG_OPT})
    if len(pos) != 1:
        raise Usage("Usage: electricidad-plan single-line F [--panel TP] [--format svg|png|pdf] [--out DIR] [--lang es|ru|en]")
    use_lang(pick_lang(opts.get("lang")))
    raw, path = load(pos[0])
    d = sanitize(raw)[0]
    tabs = [s.strip() for s in opts.get("panel", "").split(",") if s.strip()]
    ix = indexes(d)
    if any(t not in ix["panels"] for t in tabs):
        raise Usage(f"Panels: {', '.join(ix['panels']) or 'none'}.")
    if not ix["panels"]:
        raise Usage("The survey has no panels.")
    out = out_dir(path, opts)
    E, W, H = render_single_line(d, tabs)
    svg = write(os.path.join(out, "single-line" + (f"_{slug('-'.join(tabs))}" if tabs else "") + ".svg"), svg_doc(E, W, H, f"{tr('sl.short')} — {d.get('job', '')}"))
    fmt_ = opts.get("format", "png")
    conv, av = convert([svg], fmt_, os.path.splitext(svg)[0] + ".pdf")
    return report(opts, [svg] + conv, validation_warnings(raw) + av)


def cmd_sheets(argv):
    opts, pos = parse(argv, {"--tech": None, "--circuit": None, "--format": FORMATS, "--out": None, **LANG_OPT})
    if len(pos) != 1:
        raise Usage("Usage: electricidad-plan sheets F [--tech NAME | --circuit C1,C2] [--format svg|png|pdf] [--out DIR] [--lang es|ru|en]")
    use_lang(pick_lang(opts.get("lang")))
    raw, path = load(pos[0])
    d = sanitize(raw)[0]
    cs = [c for c in lst(d, "circuits") if c.get("id")]   # without an id there is nothing to point a sheet at (validate flags it)
    tech = opts.get("tech")
    if tech:
        cs = [c for c in cs if str(c.get("assigned_to") or "").strip().lower() == tech.strip().lower()]
        if cs:
            tech = str(cs[0].get("assigned_to")).strip()  # the name as written in the survey
        if not cs:
            asg = sorted({str(c.get("assigned_to")) for c in lst(d, "circuits") if c.get("assigned_to")})
            raise Usage(f"Nobody called \"{tech}\" among the assigned technicians ({', '.join(asg) or 'none'}). Assign with \"status ... --tech\".")
    if opts.get("circuit"):
        want = [s.strip() for s in opts["circuit"].split(",") if s.strip()]
        ix = indexes(d)
        if any(w not in ix["circuits"] for w in want):
            raise Usage(f"Circuits: {', '.join(ix['circuits'])}.")
        cs = [c for c in cs if c.get("id") in want]
    if not cs:
        raise Usage("No circuits to make sheets for.")
    out = out_dir(path, opts)
    fmt_ = opts.get("format", "png")
    svgs, mds, conv, av = [], [], [], []
    together, used = [], set()
    for c in cs:
        E, W, H, h = render_sheet(d, c, short_name(path))
        base = os.path.join(out, free_name(f"sheet_{slug(c.get('id'))}", used))
        svgs.append(write(base + ".svg", svg_doc(E, W, H, tr("sh.short", c=c.get("id")))))
        img = os.path.basename(base) + (".png" if fmt_ == "png" else ".svg")
        md = sheet_md(d, h, img)
        together.append(md)
        mds.append(write(base + ".md", md))
    if fmt_ == "png":
        conv, av = convert(svgs, "png", None)
        if not conv:                              # with no converter the Markdown points to the SVG, which does exist
            for m in mds:
                txt = open(m, encoding="utf-8").read().replace(".png)", ".svg)")
                write(m, txt)
    elif fmt_ == "pdf":
        dest = os.path.join(out, f"sheets_{slug(tech)}.pdf" if tech else "sheets.pdf")
        conv, av = convert(svgs, "pdf", dest)
    extra = []
    if tech:
        extra.append(write(os.path.join(out, f"sheets_{slug(tech)}.md"), "\n\n---\n\n".join(together)))
    return report(opts, svgs + mds + extra + conv, validation_warnings(raw) + av)


def cmd_dxf(argv):
    opts, pos = parse(argv, {"--floor": None, "--out": None, **LANG_OPT})
    if len(pos) != 1:
        raise Usage("Usage: electricidad-plan dxf F [--floor PB] [--out DIR] [--lang es|ru|en]")
    lang = use_lang(pick_lang(opts.get("lang")))
    raw, path = load(pos[0])
    d = sanitize(raw)[0]
    out = out_dir(path, opts)
    files, layers_ = [], {}
    for floor in floors_of(d, opts.get("floor")):
        txt, layers = dxf_floor(d, floor)
        p = os.path.join(out, f"survey_{slug(floor)}.dxf")
        d_ = os.path.dirname(p)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d_)
        with os.fdopen(fd, "w", encoding=DXF_CODEPAGE[lang][0], newline="\r\n", errors="replace") as f:
            f.write(txt)
        um = os.umask(0)
        os.umask(um)
        os.chmod(tmp, 0o666 & ~um)
        os.replace(tmp, p)
        files.append(p)
        layers_[floor] = layers
    return report(opts, files, validation_warnings(raw), {"layers": layers_})


def cmd_status(argv):
    opts, pos = parse(argv, {"--tech": None, "--note": None})
    if len(pos) != 3:
        raise Usage("Usage: electricidad-plan status F ID STATUS [--tech X] [--note TEXT]")
    path = resolve(pos[0])
    if os.path.islink(path) or not path.endswith(".json"):
        raise Usage(f"status only writes a survey .json that is a regular file (not a symlink): {path}")
    with lock(path):
        return _status(opts, pos, path)


def _status(opts, pos, path):
    d, path = load(path)
    if d.get("version") != VERSION or not isinstance(d.get("circuits"), list):
        raise Usage(f"{path} does not look like a survey (version {VERSION} and a list of circuits): not modifying it.")
    oid, st = pos[1], pos[2]
    ix = indexes(d)
    today = datetime.date.today().isoformat()
    tech = (opts.get("tech") or "").strip()[:60]
    note = re.sub(r"[\x00-\x1f\x7f]", " ", opts.get("note") or "").strip()[:300]
    warnings = []
    if oid in ix["circuits"]:
        if st not in STATUSES:
            raise Usage(f"Circuit status \"{st}\" is not valid: {', '.join(STATUSES)}.")
        c = ix["circuits"][oid]
        before = (c.get("status") or "not_surveyed")
        c["status"] = st
        if tech:
            c["assigned_to"] = tech
        if note:
            c["notes"] = (str(c.get("notes") or "") + ("; " if c.get("notes") else "") + f"{today}{' ' + tech if tech else ''}: {note}")[-2000:]
        if st == "under_repair" and not c.get("assigned_to"):
            warnings.append(f"{oid} is under repair with no technician: pass --tech (ELEC-EQU-14).")
        if st == "verified":
            meds = c.get("measurements") if isinstance(c.get("measurements"), list) else []
            ok = {m.get("type") for m in meds if isinstance(m, dict) and m.get("ok") is True}
            if not {"insulation", "pe_continuity"} <= ok:
                warnings.append(f"{oid} marked verified without insulation and PE measured and ok entered (ELEC-PLA-20).")
    elif oid in ix["points"]:
        if st not in POINT_STATUSES:
            raise Usage(f"Point status \"{st}\" is not valid: {', '.join(POINT_STATUSES)}.")
        c = ix["points"][oid]
        before = (c.get("status") or "unverified")
        c["status"] = st
        if note:
            c["note"] = (str(c.get("note") or "") + ("; " if c.get("note") else "") + f"{today}{' ' + tech if tech else ''}: {note}")[-500:]
    else:
        raise Usage(f"No circuit or point \"{oid}\". Circuits: {', '.join(ix['circuits']) or 'none'}.")
    log = d.get("log") if isinstance(d.get("log"), list) else []
    log.append({"date": today, "id": oid, "from": before, "to": st, "tech": tech or None, "note": note or None})
    d["log"] = log[-500:]
    save_json(path, d)
    if opts.get("json"):
        print(json.dumps({"file": path, "bak": path + ".bak", "id": oid, "from": before, "to": st, "warnings": warnings}, ensure_ascii=False, indent=1))
    else:
        print(f"✅ {oid}: {before} → {st}" + (f" ({tech})" if tech else "") + f". Previous copy: {path}.bak")
        for a in warnings:
            print(f"⚠️ {a}")
    return 0


def cmd_summary(argv):
    opts, pos = parse(argv, {})
    if len(pos) != 1:
        raise Usage("Usage: electricidad-plan summary F [--json]")
    raw, path = load(pos[0])
    d = sanitize(raw)[0]
    rows = []
    for c in lst(d, "circuits"):
        pts = points_of(d, c.get("id"))
        meds = [m for m in c.get("measurements", []) if isinstance(m, dict)] if isinstance(c.get("measurements"), list) else []
        rows.append({"id": c.get("id"), "name": c.get("name") or "", "device": c.get("device"), "status": (c.get("status") or "not_surveyed"),
                     "assigned_to": c.get("assigned_to") or "", "outlets": outlets(d, c.get("id")), "fault_points": sum(1 for p in pts if p.get("status") == "fault"),
                     "measurements_ok": sorted({m.get("type") for m in meds if m.get("ok") is True}),
                     "measurements_bad": sorted({m.get("type") for m in meds if m.get("ok") is False})})
    by_status = {e: [f["id"] for f in rows if f["status"] == e] for e in STATUSES}
    by_tech = {}
    for f in rows:
        if f["assigned_to"]:
            by_tech.setdefault(f["assigned_to"], []).append(f"{f['id']} ({f['status']})")
    fault_free = [f["id"] for f in rows if f["status"] == "fault" and not f["assigned_to"]]
    done = sum(1 for f in rows if f["status"] == "verified")
    if opts.get("json"):
        print(json.dumps({"file": path, "circuits": rows, "by_status": by_status, "by_tech": by_tech, "fault_unassigned": fault_free,
                          "verified": done, "total": len(rows)}, ensure_ascii=False, indent=1))
        return 0
    print(f"{d.get('job', '')}: progress {done}/{len(rows)} circuits verified")
    print(f"{'circuit':<9} {'status':<14} {'assigned':<12} {'outl.':>5} {'fault':>5}  measured")
    for f in rows:
        med = " ".join(x for x in (",".join(f["measurements_ok"]), ("BAD:" + ",".join(f["measurements_bad"])) if f["measurements_bad"] else "") if x)
        print(f"{cut(f['id'], 9):<9} {f['status']:<14} {cut(f['assigned_to'] or '-', 12):<12} {f['outlets']:>5} {f['fault_points']:>5}  {med or '-'}  {cut(f['name'], 28)}")
    print("By status: " + "; ".join(f"{e} {len(v)}" for e, v in by_status.items() if v))
    for t, v in by_tech.items():
        print(f"{t}: {', '.join(v)}")
    if fault_free:
        print(f"⚠️ In fault and unassigned: {', '.join(fault_free)}")
    return 0


def cmd_symbols(argv):
    opts, pos = parse(argv, dict(LANG_OPT))
    lang = pick_lang(opts.get("lang"))
    rows = [{"type": k, "name": v["name"]["en"], "label": v["name"][lang], "lang": lang, "source": v["source"]} for k, v in SYMBOLS.items()]
    if opts.get("json"):
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print(f"{'type':<16} {'name':<36} {'label (' + lang + ')':<36} source")
        for f in rows:
            print(f"{f['type']:<16} {f['name']:<36} {f['label']:<36} {f['source']}")
    return 0


COMMANDS = {"new": cmd_new, "validate": cmd_validate, "draw": cmd_draw, "single-line": cmd_single_line, "sheets": cmd_sheets, "dxf": cmd_dxf,
            "status": cmd_status, "summary": cmd_summary, "symbols": cmd_symbols}


def main(argv):
    if not argv or argv[0] in ("help", "-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    fn = COMMANDS.get(argv[0])
    if not fn:
        print(f"Unknown subcommand \"{argv[0]}\". Subcommands: {', '.join(COMMANDS)}. Help: electricidad-plan help")
        return 2
    rest = argv[1:]
    if any(a in ("--help", "-h") and (i == 0 or not rest[i - 1].startswith("--") or rest[i - 1] == "--json") for i, a in enumerate(rest)):
        print("\n".join(ln for ln in __doc__.splitlines() if ln.startswith(f"  electricidad-plan {argv[0]} ")))
        print("Full help: electricidad-plan help")
        return 0
    try:
        return fn(argv[1:])
    except Usage as e:
        print(str(e))
        return 2
    except OSError as e:
        print(f"Could not read/write: {type(e).__name__}: {e.strerror or e}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
