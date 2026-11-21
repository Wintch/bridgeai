#!/usr/bin/env python3
"""Offline checks for electricidad_plan.py (`gateway electricidad plan`): the worked example, every subcommand in a temp dir, SVG that parses
as XML, DXF sections and layers, seeded errors that `validate` must catch, atomic `status` with .bak, PNG/PDF skipped with a warning when
no converter is on PATH, and person-facing text in es, en and ru (--lang and the prefs fallback). Run: python3 -I electricidad_plan_selftest.py"""
import contextlib, copy, importlib.util, io, json, os, re, shutil, subprocess, sys, tempfile, threading
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "electricidad_plan.py")
EXAMPLE = os.path.join(HERE, "electricidad", "examples", "house-panel-photo.json")
tmp = tempfile.mkdtemp()
NO_PREFS = os.path.join(tmp, "no-prefs.json")                 # never created: the language falls back to es
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append("FAIL " + name)


os.environ["AIBRIDGE_PREFS"] = NO_PREFS
spec = importlib.util.spec_from_file_location("electricidad_plan", SCRIPT)
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)


def run(*args, path=None, prefs=NO_PREFS):
    """Run the CLI as a subprocess (real PATH lookups for converters); returns (code, stdout)."""
    env = dict(os.environ, ELECTRICIDAD_DIR=os.path.join(tmp, "jobs"), AIBRIDGE_PREFS=prefs)
    if path is not None:
        env["PATH"] = path
    r = subprocess.run([sys.executable, "-I", SCRIPT] + list(args), capture_output=True, text=True, env=env, timeout=600)
    return r.returncode, r.stdout + r.stderr


def call(*args):
    """Run main() in-process (fast); returns (code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = ep.main(list(args))
    return code, buf.getvalue()


def svg_ok(p):
    try:
        root = ET.parse(p).getroot()
        return root.tag.endswith("svg")
    except (ET.ParseError, OSError):
        return False


def texts(p):
    return " ".join("".join(e.itertext()) for e in ET.parse(p).getroot().iter() if e.tag.endswith("text"))


def write(name, d):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    return p


# ---------------------------------------------------------------- the worked example
base = json.load(open(EXAMPLE, encoding="utf-8"))
F = ep.validate(base)
check("example: validate with no errors", not [f for f in F if f["status"] == "fail"])
checks = {f["check"] for f in F}
check("example: warns about the single RCD for every circuit (ELEC-REV-10)", "single_rcd" in checks)
check("example: warns about outlet points with no circuit", "point_no_circuit" in checks)
check("example: every finding has a rule and a status", all(f["rule"] and f["status"] in ("fail", "warn") for f in F))
check("example: labels from the photo", {"TERMICA GRAL", "ILUM COCINA", "PILETA", "PORTON", "L EXT CONTR"} <= {p.get("label") for p in base["devices"]})
check("example: unreadable MCBs marked", sum(1 for p in base["devices"] if p.get("label") == "illegible") >= 3)
check("example: source is a by-eye sketch", base["source"] == "by-eye sketch")
code, out = run("validate", EXAMPLE, "--json")
j = json.loads(out)
check("validate CLI: exit 0 and JSON", code == 0 and j["errors"] == 0 and j["warnings"] > 0)

ej = os.path.join(tmp, "ej", "survey.json")
os.makedirs(os.path.dirname(ej))
shutil.copy(EXAMPLE, ej)
outd = os.path.join(tmp, "ej", "output")

# ---------------------------------------------------------------- draw / single-line / sheets / dxf (SVG only: fast, in-process)
code, out = call("draw", ej, "--format", "svg", "--lang", "en", "--json")
files = json.loads(out)["files"]
check("draw: writes the SVG next to the JSON (output/)", code == 0 and files and all(a.startswith(outd) for a in files))
check("draw: SVG is valid XML", all(svg_ok(a) for a in files))
check("draw: output readable by the group (not 0600)", all(os.stat(a).st_mode & 0o044 for a in files))
check("draw: file name plan_PB_circuit.svg", files[0].endswith("plan_PB_circuit.svg"))
t = texts(files[0])
check("draw: by-eye sketch title block", "Approximate sketch, not to scale" in t)
check("draw: legend with symbol names", "Ceiling outlet point (center)" in t and "Socket outlet 2P+E 10 A" in t and "Main panel" in t)
check("draw: rooms with name and dimensions", "Kitchen-dining" in t and "≈ 4 × 6 m" in t)
check("draw: every point with id and circuit", "p1·IUG1 a" in t)
check("draw: circuit text label on the run (not just color), decimal point in en", "IUG9 2x1.5+T2.5" in t)
svgtxt = open(files[0], encoding="utf-8").read()
check("draw: explicit stroke-opacity after stroke (ImageMagick)", 'stroke="#333" stroke-opacity="1"' in svgtxt)
check("draw: no rotated texts and no <pattern>", "rotate(" not in svgtxt and "<pattern" not in svgtxt)
code, out = call("draw", ej, "--format", "svg", "--color", "status", "--lang", "en", "--json")
ps_ = json.loads(out)["files"][0]
check("draw --color status", code == 0 and ps_.endswith("plan_PB_status.svg") and svg_ok(ps_) and "UNDER REPAIR" in texts(ps_))
code, out = call("draw", ej, "--format", "svg", "--only", "ACU1,IUG9", "--lang", "en", "--json")
po = json.loads(out)["files"][0]
check("draw --only: isolated sheet", code == 0 and "only-ACU1-IUG9" in po and svg_ok(po) and "Circuits on this sheet" in texts(po))
check("draw --only: dims the rest", "#BDBDBD" in open(po, encoding="utf-8").read())
code, out = call("draw", ej, "--only", "NOSUCH")
check("draw --only with a missing circuit → 2", code == 2)
code, out = call("draw", ej, "--floor", "P9")
check("draw --floor missing → 2", code == 2)
code, out = call("draw", ej, "--color", "rainbow")
check("draw --color invalid → 2", code == 2)
code, out = call("sheets", "--help")
check("SUBCOMMAND --help prints that subcommand's usage line", code == 0 and "electricidad-plan sheets F [--tech NAME" in out and "draw F" not in out)
code, out = call("status", os.path.join(tmp, "nojob.json"), "C1", "repaired", "--note", "--help")
check("--help as an option's value is not taken as help", code == 2 and "Full help" not in out)
code, out = call("draw", ej, "--lang", "fr")
check("draw --lang invalid → 2", code == 2)

code, out = call("single-line", ej, "--format", "svg", "--lang", "en", "--json")
pu = json.loads(out)["files"][0]
tu = texts(pu)
check("single-line: valid SVG named single-line.svg", code == 0 and svg_ok(pu) and pu.endswith("single-line.svg"))
check("single-line: main → RCD → MCB with In, curve, IΔn and section", "MCB 4P C40" in tu and "RCD 4P 63 A 30 mA" in tu and "2P C10" in tu
      and "2x1.5+T2.5" in tu)
check("single-line: circuits with status", "IUG9" in tu and "UNDER REPAIR" in tu)

code, out = call("sheets", ej, "--tech", "technician b", "--format", "svg", "--lang", "en", "--json")
ah = json.loads(out)["files"]
mds = [a for a in ah if a.endswith(".md")]
check("sheets --tech: one sheet per assigned circuit + joint Markdown", code == 0 and any("sheet_ACU1.svg" in a for a in ah)
      and any("sheet_APM1.svg" in a for a in ah) and any(a.endswith("sheets_Technician-B.md") for a in ah))
check("sheets: valid SVGs", all(svg_ok(a) for a in ah if a.endswith(".svg")))
md = open([m for m in mds if m.endswith("sheet_ACU1.md")][0], encoding="utf-8").read()
check("sheets: device to lock out", 'P26 "PILETA"' in md and "Lock out" in md)
check("sheets: table of outlet points", "| p69 | Pump |" in md)
check("sheets: pending measurements", "Insulation resistance with a megohmmeter" in md and "0.2 MOhm" in md)
check("sheets: lockout checklist with rules", "- [ ]" in md and "ELEC-SEG-5" in md and "ELEC-EQU-21" in md)
check("sheets: others working", "Technician A" in md)
check("sheets: image points to the SVG when svg was asked", "sheet_ACU1.svg)" in md)
check("sheets: status command uses the new verbs", "gateway electricidad plan status" in md and "repaired --tech" in md)
code, out = call("sheets", ej, "--tech", "Nobody")
check("sheets --tech unknown → 2", code == 2)
code, out = call("sheets", ej, "--circuit", "TUG3", "--format", "svg")
check("sheets --circuit", code == 0 and "sheet_TUG3.svg" in out)

code, out = call("dxf", ej, "--lang", "en", "--json")
jd = json.loads(out)
pd = jd["files"][0]
raw = open(pd, "rb").read()
txt = raw.decode("cp1252")
lines = txt.splitlines()
pairs = list(zip(lines[0::2], lines[1::2]))
secs = [v for (c, v), (c2, v2) in zip(pairs, pairs[1:]) if c.strip() == "0" and v == "SECTION" for v in [v2] if c2.strip() == "2"]
check("dxf: file survey_PB.dxf", pd.endswith("survey_PB.dxf"))
check("dxf: R12 (AC1009) and code page", "AC1009" in txt and "ANSI_1252" in txt)
check("dxf: code/value pairs", len(lines) % 2 == 0 and all(c.strip().lstrip("-").isdigit() for c, _ in pairs))
check("dxf: sections HEADER, TABLES, BLOCKS, ENTITIES and EOF", secs == ["HEADER", "TABLES", "BLOCKS", "ENTITIES"] and pairs[-1] == ("  0", "EOF"))
layers = [v for (c, v), (c2, v2) in zip(pairs, pairs[1:]) if c.strip() == "0" and v == "LAYER" for v in [v2] if c2.strip() == "2"]
want = {"ROOMS", "DIMENSIONS", "PANELS", "TEXT"} | {f"CIRC_{c['id']}" for c in base["circuits"]}
check("dxf: layers ROOMS, DIMENSIONS, PANELS, TEXT and one per circuit", want <= set(layers))
used = {v for (c, v) in pairs if c.strip() == "8"}
check("dxf: entities on declared layers", used <= set(layers) and "CIRC_ACU1" in used and "ROOMS" in used)
check("dxf: POLYLINE closed with VERTEX/SEQEND, TEXT and CIRCLE", txt.count("POLYLINE") == txt.count("SEQEND") > 0 and "\nTEXT" in txt and "\nCIRCLE" in txt)
check("dxf: English text in en", "Approximate sketch, not to scale" in txt and "approx. 18 m" in txt)
acc = copy.deepcopy(base)
acc["rooms"][2]["name"] = "Galería"
pacc = os.path.join(tmp, "acc", "survey.json")
os.makedirs(os.path.dirname(pacc))
json.dump(acc, open(pacc, "w", encoding="utf-8"), ensure_ascii=False)
code, out = call("dxf", pacc, "--lang", "es", "--json")
rawa = open(json.loads(out)["files"][0], "rb").read()
check("dxf es: CRLF lines and accents in cp1252", b"\r\n" in rawa and "Galería".encode("cp1252") in rawa and b"aprox." in rawa)
code, out = call("dxf", pacc, "--lang", "ru", "--json")
rawr = open(json.loads(out)["files"][0], "rb").read()
check("dxf ru: code page 1251 with Cyrillic text, accents of typed data folded (Galería → Galeria)",
      b"ANSI_1251" in rawr and "Этаж:".encode("cp1251") in rawr and b"Galeria" in rawr)

# ---------------------------------------------------------------- new
code, out = run("new", "Test House", "--json")
jn = json.loads(out)
pn = jn["files"][0]
check("new: creates JOB/survey.json under ELECTRICIDAD_DIR", code == 0 and pn == os.path.join(tmp, "jobs", "test-house", "survey.json"))
check("new: valid template", ep.validate(json.load(open(pn, encoding="utf-8"))) is not None
      and not [f for f in ep.validate(json.load(open(pn, encoding="utf-8"))) if f["status"] == "fail"])
check("new: template names in the default language (es)", json.load(open(pn, encoding="utf-8"))["floors"][0]["name"] == "Planta baja")
code, out = run("new", "Test House")
check("new: does not overwrite an existing job → 2", code == 2 and "already exists" in out)
code, out = run("validate", "test-house")
check("validate by job name", code == 0)
code, out = call("new", "../../etc", "--dir", os.path.join(tmp, "x"), "--lang", "en")
check("new: name without path traversal", code == 0 and os.path.exists(os.path.join(tmp, "x", "etc", "survey.json")))
check("new --lang en: English template names", json.load(open(os.path.join(tmp, "x", "etc", "survey.json")))["panels"][0]["name"] == "Main panel")

# ---------------------------------------------------------------- validate: seeded errors
d = copy.deepcopy(base)
d["points"].append(dict(d["points"][0]))                                      # duplicate id
d["points"][1]["circuit"] = "NOSUCH"                                          # broken reference
d["points"][2]["x"], d["points"][2]["y"] = 50, 50                             # point outside its room
c = next(c for c in d["circuits"] if c["id"] == "IUG1")
c["section_mm2"] = 1.0                                                        # 1 mm² with C10 on an IUG: minimum 1.5
t = next(c for c in d["circuits"] if c["id"] == "TUG2")
next(p for p in d["devices"] if p["id"] == t["device"])["in_a"] = 25          # C25 on 2.5 mm² (Iz 21 A)
next(c for c in d["circuits"] if c["id"] == "IUG6")["assigned_to"] = ""
next(c for c in d["circuits"] if c["id"] == "IUG6")["status"] = "under_repair"
d["circuits"].append({"id": "NODEV", "type": "TUG", "name": "no device", "device": None, "section_mm2": 2.5})
d["devices"].append({"id": "PX", "panel": "TP", "type": "MCB", "poles": 2, "in_a": 16, "curve": "C", "upstream": None})
d["circuits"].append({"id": "NORCD", "type": "TUG", "name": "no RCD", "device": "PX", "section_mm2": 2.5})
d["points"].append({"id": "pbx", "type": "socket", "floor": "PB", "room": "lav", "x": 15, "y": 19, "circuit": "NORCD"})
d["runs"].append({"circuit": "IUG1", "sequence": ["TP", "ghost"]})
for k in range(16):                                                           # 16 more outlet points on TUG4 (max. 15)
    d["points"].append({"id": f"extra{k}", "type": "socket", "floor": "PB", "room": "est", "x": 5 + k * 0.2, "y": 17, "circuit": "TUG4"})
pv = write("seeded.json", d)
code, out = run("validate", pv, "--json")
jv = json.loads(out)
got = {f["check"] for f in jv["findings"]}
check("validate seeded: exit 1", code == 1 and jv["errors"] > 0)
for name in ("duplicate_id", "broken_reference", "point_outside", "mcb_over_cable", "min_section", "no_device", "no_rcd30",
             "wet_socket_no_rcd", "unassigned", "outlet_count"):
    check(f"validate catches {name}", name in got)
rule = {f["check"]: f["rule"] for f in jv["findings"]}
check("validate: cites the guide rule", rule.get("mcb_over_cable") == "ELEC-PRO-4" and rule.get("no_rcd30") == "ELEC-PRO-7")
check("validate: evidence in English with a decimal point", any("1 mm² is less than the minimum for a IUG (1.5 mm²" in f["evidence"] for f in jv["findings"]))
code, out = call("draw", pv, "--format", "svg", "--out", os.path.join(tmp, "s2"))
check("draw with errors: draws anyway and warns", code == 0 and "error(s)" in out)
pbad = os.path.join(tmp, "broken.json")
open(pbad, "w").write("{ this is not json")
code, out = call("validate", pbad)
check("broken JSON → 2 with line and column", code == 2 and "line" in out and "column" in out)
code, out = call("validate", os.path.join(tmp, "no-such.json"))
check("missing file → 2", code == 2)
hostile = copy.deepcopy(base)
hostile["job"] = '<script>alert(1)</script> & "x"'
hostile["rooms"][0]["name"] = "</text><svg onload=1>"
ph = write("hostile.json", hostile)
code, out = call("draw", ph, "--format", "svg", "--out", os.path.join(tmp, "s3"), "--json")
phs = json.loads(out)["files"][0]
check("JSON texts escaped in the SVG", svg_ok(phs) and "<script>" not in open(phs, encoding="utf-8").read())
check("validate warns about personal data in the job name", "personal_data" in {f["check"] for f in ep.validate(dict(base, job="House 11 4567 8901"))})

# ---------------------------------------------------------------- status: atomic, .bak, log
before = open(ej, encoding="utf-8").read()
os.chmod(ej, 0o664)
mode_before = os.stat(ej).st_mode & 0o777
code, out = run("status", ej, "IUG10", "under_repair", "--tech", "Technician C", "--note", "replacing stake lights", "--json")
je = json.loads(out)
new = json.load(open(ej, encoding="utf-8"))
c10 = next(c for c in new["circuits"] if c["id"] == "IUG10")
check("status: updates status and assigned_to", code == 0 and c10["status"] == "under_repair" and c10["assigned_to"] == "Technician C")
check("status: note with date and technician", "Technician C: replacing stake lights" in c10["notes"])
check("status: leaves .bak equal to the previous file", open(ej + ".bak", encoding="utf-8").read() == before)
check("status: log", new["log"][-1]["id"] == "IUG10" and new["log"][-1]["from"] == "fault" and new["log"][-1]["to"] == "under_repair"
      and je["from"] == "fault")
check("status: keeps the JSON permissions (not 0600)", (os.stat(ej).st_mode & 0o777) == mode_before)
check("status: no temp files left", not [f for f in os.listdir(os.path.dirname(ej)) if f.startswith(".tmp-")])
code, out = call("status", ej, "p69", "ok")
check("status of a point", code == 0 and next(p for p in json.load(open(ej))["points"] if p["id"] == "p69")["status"] == "ok")
code, out = call("status", ej, "IUG10", "almost")
check("invalid status → 2 without touching the file", code == 2 and json.load(open(ej))["circuits"][-4]["status"] != "almost")
code, out = call("status", ej, "NOSUCH", "fault")
check("status of a missing id → 2", code == 2)
code, out = call("status", ej, "ACU2", "under_repair")
check("status under_repair with no technician warns", code == 0 and "ELEC-EQU-14" in out)
code, out = call("status", ej, "IUG1", "verified")
check("status verified with no measurements warns", code == 0 and "ELEC-PLA-20" in out)
# atomic write: if it fails half way, the original stays intact
orig = open(ej, encoding="utf-8").read()
real_replace = os.replace
try:
    def boom(*a):
        raise OSError(28, "No space left on device")
    os.replace = boom
    try:
        ep.save_json(ej, {"version": 1})
        raised = False
    except OSError:
        raised = True
finally:
    os.replace = real_replace
check("atomic write: a failure does not leave the JSON half written", raised and open(ej, encoding="utf-8").read() == orig
      and not [f for f in os.listdir(os.path.dirname(ej)) if f.startswith(".tmp-")])

# ---------------------------------------------------------------- summary / symbols
code, out = call("summary", ej, "--json")
jr = json.loads(out)
check("summary: by circuit, technician and status", code == 0 and jr["total"] == len(base["circuits"]) and "Technician B" in jr["by_tech"]
      and "IUG10" in jr["by_status"]["under_repair"])
code, out = call("summary", ej)
check("summary text", code == 0 and "verified" in out and "Technician A" in out)
code, out = call("symbols", "--json")
js = json.loads(out)
check("symbols: each with name, label and source", code == 0 and all(s["name"] and s["label"] and s["source"] for s in js))
check("symbols: cover every point type", set(ep.POINT_TYPES) <= set(ep.SYMBOLS))
check("symbols: every symbol named in es, ru and en", all(set(v["name"]) == set(ep.LANGS) and all(v["name"].values()) for v in ep.SYMBOLS.values()))
code, out = call("symbols", "--lang", "ru", "--json")
check("symbols --lang ru: label in Russian", code == 0 and next(s for s in json.loads(out) if s["type"] == "socket")["label"] == "Розетка 2P+PE 10 A")

# ---------------------------------------------------------------- languages: the same content in es, ru and en
RULE_ID = re.compile(r"ELEC-[A-Z]{3}-\d+")
check("string table: es, ru and en have the same keys", set(ep.TXT["es"]) == set(ep.TXT["en"]) == set(ep.TXT["ru"]))
check("string table: no empty strings", all(v for L in ep.TXT.values() for v in L.values()))
check("string table: every rule ID of the sheet text is in all three languages",
      all(sorted(RULE_ID.findall(str(ep.TXT[L][k]))) == sorted(RULE_ID.findall(str(ep.TXT["es"][k]))) for L in ("en", "ru") for k in ep.TXT["es"]))
LANG_WORDS = {"es": ("BLOQUEAR ANTES DE TOCAR NADA", "Checklist de consignación", "Croquis orientativo, no a escala", "Bomba", "aislación"),
              "en": ("LOCK OUT BEFORE TOUCHING ANYTHING", "Lockout checklist", "Approximate sketch, not to scale", "Pump", "insulation"),
              "ru": ("ЗАБЛОКИРОВАТЬ, ПРЕЖДЕ ЧЕМ ЧТО-ЛИБО ТРОГАТЬ", "Чек-лист отключения и блокировки", "Ориентировочный эскиз, не в масштабе", "Насос", "изоляция")}
for lang, words in LANG_WORDS.items():
    code, out = call("sheets", ej, "--circuit", "ACU1", "--format", "svg", "--lang", lang, "--out", f"lang-{lang}", "--json")
    fs = json.loads(out)["files"]
    tl = texts([a for a in fs if a.endswith(".svg")][0])
    mdl = open([a for a in fs if a.endswith(".md")][0], encoding="utf-8").read()
    others = [w for L, ws in LANG_WORDS.items() if L != lang for w in ws[:3]]
    check(f"sheets --lang {lang}: sheet labels in {lang} (SVG and Markdown)", code == 0 and all(w in tl for w in words)
          and words[0].lower() in mdl.lower() and not any(w in tl for w in others))
    check(f"sheets --lang {lang}: complete safety checklist (7 items + rules)", tl.count("ELEC-SEG-") >= 4 and "ELEC-EQU-27" in tl and "ELEC-PLA-21" in tl)
prefs_ru = os.path.join(tmp, "prefs-ru.json")
json.dump({"lang": "ru"}, open(prefs_ru, "w"))
code, out = run("draw", ej, "--format", "svg", "--out", "prefs", "--json", prefs=prefs_ru)
check("no --lang: the prefs file decides (ru)", code == 0 and "Условные обозначения" in texts(json.loads(out)["files"][0]))
code, out = run("draw", ej, "--format", "svg", "--out", "noprefs", "--json")
tn = texts(json.loads(out)["files"][0])
check("no --lang and no prefs: es (decimal comma)", code == 0 and "Referencias" in tn and "IUG9 2x1,5+T2,5" in tn)
code, out = run("draw", ej, "--format", "svg", "--out", "explicit", "--lang", "en", "--json", prefs=prefs_ru)
check("--lang beats the prefs file", code == 0 and "Legend" in texts(json.loads(out)["files"][0]))
code, out = run("validate", EXAMPLE, prefs=prefs_ru)
check("tool output stays English whatever the prefs say", "warning(s)" in out and "No errors." in out)

# ---------------------------------------------------------------- regressions from the review (one test per bug)
GUIDE = os.path.join(HERE, "electricidad")
if os.path.isdir(GUIDE):                                     # every rule cited exists as a heading in the guide
    heads = set()
    for fn in os.listdir(GUIDE):
        if fn.endswith(".md"):
            heads |= set(re.findall(r"^###\s+(ELEC-[A-Z]{3}-\d+):", open(os.path.join(GUIDE, fn), encoding="utf-8").read(), re.M))
    cited = set(RULE_ID.findall(open(SCRIPT, encoding="utf-8").read()))
    check(f"rules cited exist in the guide (missing: {sorted(cited - heads)})", cited <= heads)


def job(name, d=None, raw=None):
    """Create tmp/rev/NAME/survey.json and return its path."""
    p = os.path.join(tmp, "rev", name, "survey.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(raw if raw is not None else json.dumps(d, ensure_ascii=False))
    return p


# BOM from Windows editors: accepted
pb = job("bom", raw="﻿" + json.dumps(base, ensure_ascii=False))
check("JSON with BOM is read (before: 'not valid JSON')", call("validate", pb)[0] == 0)
# JSON nested too deep: 2, no traceback
code, out = run("validate", job("nested", raw="[" * 100000 + "]" * 100000))
check("JSON nested too deep → 2 with no traceback", code == 2 and "Traceback" not in out)
# fields with odd types: before, TypeError (unhashable dict) in validate, draw, sheets and dxf
odd = {"version": 1, "floors": [{"id": "PB"}], "rooms": [{"id": {"a": 1}, "floor": "PB", "polygon": [[0, 0], [3, 0], [3, 3]]}],
       "panels": [1, None, {"id": "TP", "floor": ["PB"], "x": 0, "y": 0}],
       "devices": [{"id": 5, "panel": "TP", "type": ["MCB"], "in_a": "ten"}],
       "circuits": [{"id": ["x"], "device": {"a": 1}, "measurements": "x", "status": {}}, {"id": "C1", "type": "TUG", "device": "5"}],
       "points": [{"id": "p", "x": "a", "y": None, "type": ["t"], "circuit": ["c"], "floor": {"a": 1}}],
       "runs": [{"circuit": "C1", "sequence": [None, 1, [2], {"a": 1}, "TP"]}]}
pr = job("odd", odd)
for sub in (["validate"], ["draw", "--format", "svg"], ["single-line", "--format", "svg"], ["sheets", "--format", "svg"], ["dxf"], ["summary"]):
    code, out = run(sub[0], pr, *sub[1:])
    check(f"fields with odd types: {sub[0]} with no traceback (exit {code})", code in (0, 1, 2) and "Traceback" not in out)
check("validate reports data_type", "data_type" in {f["check"] for f in ep.validate(odd)})
# `new "Test House"` creates test-house/: looking it up by the same name has to work
code, out = run("validate", "Test House")
check("validate by the name as given to new (capitals and space)", code == 0)
# --out outside the job folder: refused, and nothing created outside
outside = os.path.join(tmp, "outside-the-job")
code, out = call("draw", ej, "--format", "svg", "--out", outside)
check("--out absolute outside the job → 2 and the folder is not created", code == 2 and not os.path.exists(outside))
code, out = call("draw", ej, "--format", "svg", "--out", "../../outside2")
check("--out with .. → 2", code == 2 and not os.path.exists(os.path.join(tmp, "outside2")))
os.symlink(tmp, os.path.join(tmp, "ej", "trap"))
code, out = call("dxf", ej, "--out", "trap")
check("--out that is a symlink to the outside → 2", code == 2 and not os.path.exists(os.path.join(tmp, "survey_PB.dxf")))
code, out = call("draw", ej, "--format", "svg", "--out", "other", "--json")
check("--out relative stays inside the job", code == 0 and json.loads(out)["files"][0].startswith(os.path.join(tmp, "ej", "other")))
# .bak that is a symlink: shutil.copy2 used to write through the link (outside the job)
pe_ = job("bak", copy.deepcopy(base))
victim = os.path.join(tmp, "victim.txt")
open(victim, "w").write("do not touch")
os.symlink(victim, pe_ + ".bak")
code, out = call("status", pe_, "IUG1", "surveyed")
check("status: a .bak symlink is not followed (the outside file stays intact)", code == 0 and open(victim).read() == "do not touch"
      and not os.path.islink(pe_ + ".bak"))
# status on a symlink or on a JSON that is not a survey: refused
link = os.path.join(tmp, "rev", "bak", "link.json")
os.symlink(pe_, link)
check("status on a symlink → 2", call("status", link, "IUG1", "measured")[0] == 2)
other = job("other", {"circuits": [{"id": "IUG1"}]})
check("status on a JSON without version 1 → 2 without touching it", call("status", other, "IUG1", "fault")[0] == 2
      and json.load(open(other)) == {"circuits": [{"id": "IUG1"}]})
# concurrent status (several technicians at once): lock, no update is lost
pc = job("concurrent", copy.deepcopy(base))
ids = [c["id"] for c in base["circuits"]][:8]
threads = [threading.Thread(target=run, args=("status", pc, i, "measured")) for i in ids]
[h.start() for h in threads]
[h.join() for h in threads]
fin = {c["id"]: c["status"] for c in json.load(open(pc, encoding="utf-8"))["circuits"]}
check("concurrent status: all 8 updates remain", all(fin[i] == "measured" for i in ids)
      and len(json.load(open(pc, encoding="utf-8"))["log"]) == 8)
# survey with no floors: it used to exit 0 without writing anything
check("draw with no floors → 2", call("draw", job("nofloors", {"version": 1}), "--format", "svg")[0] == 2)
# ids that give the same file or layer name
dup = copy.deepcopy(base)
c0 = next(c for c in dup["circuits"] if c["id"] == "IUG1")
dup["circuits"].append(dict(c0, id="IUG 1"))
for c in dup["circuits"]:
    if c["id"] in ("IUG1", "IUG 1"):
        c["id"] = "C 1" if c["id"] == "IUG1" else "C-1"
pd2 = job("dup", dup)
code, out = call("sheets", pd2, "--circuit", "C 1,C-1", "--format", "svg", "--json")
hs = [a for a in json.loads(out)["files"] if a.endswith(".svg")]
check("sheets: two ids with the same slug do not overwrite each other", code == 0 and len(set(hs)) == 2)
code, out = call("dxf", pd2, "--json")
layers_dup = json.loads(out)["layers"]["PB"]
check("dxf: no repeated layers, and layer 0 present", len(layers_dup) == len(set(layers_dup)) and "0" in layers_dup)
# dxf: the overall dimension measures the rooms, not from the origin (it used to add 0,0 and the points)
off = copy.deepcopy(base)
off["rooms"] = [{"id": "a", "name": "Odd ^ room\r\nline", "floor": "PB", "polygon": [[50, 50], [54, 50], [54, 53], [50, 53]]}]
off["points"] = [{"id": "q1", "type": "socket", "floor": "PB", "room": "a", "x": 51, "y": 50.1, "circuit": "TUG2"}]
off["panels"] = [dict(off["panels"][0], x=50.2, y=52.5)]
po_ = job("offset", off)
code, out = call("dxf", po_, "--lang", "en", "--json")
dtxt = open(json.loads(out)["files"][0], encoding="cp1252").read()
dl = dtxt.splitlines()
check("dxf: overall dimension = width of the rooms (≈ 4 m)", "approx. 4 m" in dtxt and "approx. 54 m" not in dtxt)
check("dxf: texts with no line breaks and no raw ^ (pairs intact)", len(dl) % 2 == 0
      and all(c.strip().lstrip("-").isdigit() for c in dl[0::2]) and "Odd ^  room  line" in dtxt)
# single-line: devices in a cycle are drawn anyway (they used to disappear)
cyc = {"version": 1, "floors": [{"id": "PB"}], "panels": [{"id": "TP", "floor": "PB", "x": 0, "y": 0}],
       "devices": [{"id": "X1", "panel": "TP", "type": "MCB", "in_a": 10, "upstream": "X2"},
                   {"id": "X2", "panel": "TP", "type": "RCD", "in_a": 40, "idn_ma": 30, "upstream": "X1"}],
       "circuits": [{"id": "C1", "type": "TUG", "device": "X1", "section_mm2": 2.5}]}
code, out = call("single-line", job("cycle", cyc), "--format", "svg", "--lang", "en", "--json")
tc = texts(json.loads(out)["files"][0])
check("single-line: devices in a cycle appear", code == 0 and "X1" in tc and "X2" in tc)
check("single-line: MCB with no curve reads \"10 A\"", "MCB 10 A" in tc)
check("validate: the cycle is reported", "cycle" in {f["check"] for f in ep.validate(cyc)})
# validate rules as corrected
mb = copy.deepcopy(base)
mb["devices"].append({"id": "PM", "panel": "TP", "type": "MCB", "poles": 2, "in_a": 10, "curve": "C"})
mb["circuits"].append({"id": "MB1", "type": "MBTF", "device": "PM", "section_mm2": 1.5, "pe_mm2": 2.5})
check("MBTF with no 30 mA RCD is an error too (ELEC-PRO-7: every final circuit)",
      any(f["check"] == "no_rcd30" and f["ref"] == "MB1" for f in ep.validate(mb)))
wet = copy.deepcopy(base)
wet["devices"].append({"id": "PH", "panel": "TP", "type": "MCB", "poles": 2, "in_a": 16, "curve": "C"})
wet["circuits"].append({"id": "TH", "type": "TUG", "device": "PH", "section_mm2": 2.5, "pe_mm2": 1.5})
wet["points"].append({"id": "ph1", "type": "outdoor_socket", "floor": "PB", "room": "lav", "x": 15, "y": 19, "circuit": "TH"})
fh = ep.validate(wet)
check("wet socket with no RCD cites ELEC-PRO-7 (not ELEC-ESP-29, which is about heights)",
      any(f["check"] == "wet_socket_no_rcd" and f["rule"] == "ELEC-PRO-7" for f in fh))
check("outdoor socket on a TUG warns ELEC-CIR-11", any(f["check"] == "outdoor_socket_general" and f["ref"] == "ph1" for f in fh))
pe25 = copy.deepcopy(base)
next(c for c in pe25["circuits"] if c["id"] == "TUG2")["section_mm2"] = 4
next(c for c in pe25["circuits"] if c["id"] == "TUG2")["pe_mm2"] = 2.5
check("PE smaller than the phase (≤ 16 mm²) warns ELEC-CON-6", any(f["check"] == "small_pe" and f["ref"] == "TUG2" for f in ep.validate(pe25)))
cm = copy.deepcopy(base)
cm["rooms"][0]["polygon"] = [[0, 0], [400, 0], [400, 600], [0, 600]]
check("room 600 m on a side: centimeters warning", "scale" in {f["check"] for f in ep.validate(cm)})
# sheet: the cut if the panel is opened is the main switch, not the intermediate RCD; command quoted when needed
h = ep.sheet_content(base, next(c for c in base["circuits"] if c["id"] == "ACU1"), "/jobs/house with space/survey.json", lang="en")
check("sheet: if the panel is opened, the main switch (CG) is switched off", "main switch (CG)" in h["checklist"][0])
check("sheet: status command with the path in quotes", "'/jobs/house with space/survey.json'" in h["status_cmd"])
# final review: RCD with unknown IΔn is not reported as "no RCD"; poles not surveyed are not drawn double-pole
nd = copy.deepcopy(base)
next(p for p in nd["devices"] if p["id"] == "ID1")["idn_ma"] = None
fv = [f for f in ep.validate(nd) if f["ref"] == "IUG1"]
check("validate: RCD with no IΔn → \"rcd30_unconfirmed\" (missing data, still an error), not \"no_rcd30\"",
      any(f["check"] == "rcd30_unconfirmed" and f["status"] == "fail" and "ID1" in f["evidence"] for f in fv)
      and not any(f["check"] == "no_rcd30" for f in fv))
np_ = copy.deepcopy(base)
next(p for p in np_["devices"] if p["id"] == "P01")["poles"] = None
Eu = []
ep._dev_symbol(Eu, {"type": "MCB", "poles": None}, 50, 50)
check("single-line: poles not surveyed → \"?\" and no ticks", any(">?<" in e for e in Eu) and sum("stroke-width=\"1.6\"" in e for e in Eu) == 0)
Eb = []
ep._dev_symbol(Eb, {"type": "MCB", "poles": 2}, 50, 50)
check("single-line: known double-pole → two ticks", sum("stroke-width=\"1.6\"" in e for e in Eb) == 2)
hp = ep.sheet_content(np_, next(c for c in np_["circuits"] if c["id"] == "IUG1"), "/jobs/x/survey.json", lang="en")
check("sheet: poles not surveyed → lock out the main switch too (ELEC-EQU-24)",
      any("whether it is double-pole was not surveyed" in x and "ELEC-EQU-24" in x for x in hp["checklist"]))
# more than 15 circuits: the second round of colors is told apart and explained
check("plan: repeated colors are told apart (white center) and the legend says so", "white center" in texts(files[0]))

# ---------------------------------------------------------------- PNG/PDF: with no converter they are skipped with a warning
empty = os.path.join(tmp, "no-path")
os.makedirs(empty)
code, out = run("draw", ej, "--format", "png", "--out", os.path.join(tmp, "ej", "s4"), "--json", path=empty)
jp = json.loads(out)
check("no typst or ImageMagick: PNG skipped with a warning and the SVG anyway", code == 0 and all(a.endswith(".svg") for a in jp["files"])
      and any("only the SVGs remain" in a for a in jp["warnings"]))
code, out = run("sheets", ej, "--circuit", "ACU1", "--format", "png", "--out", os.path.join(tmp, "ej", "s5"), "--json", path=empty)
jp = json.loads(out)
mdp = [a for a in jp["files"] if a.endswith(".md")][0]
check("no converter: the sheet's Markdown points to the SVG", code == 0 and "sheet_ACU1.svg)" in open(mdp, encoding="utf-8").read())
code, out = run("single-line", ej, "--format", "pdf", "--out", os.path.join(tmp, "ej", "s6"), "--json", path=empty)
check("no converter: PDF skipped with a warning", code == 0 and "PDF skipped" in out)
conv = [h for h in ("typst", "rsvg-convert", "magick", "convert", "inkscape") if shutil.which(h)]
if conv:
    code, out = run("single-line", ej, "--format", "png", "--out", os.path.join(tmp, "ej", "s7"), "--json")
    jp = json.loads(out)
    png = [a for a in jp["files"] if a.endswith(".png")]
    check(f"with {conv[0]}: PNG generated", code == 0 and png and open(png[0], "rb").read(8) == b"\x89PNG\r\n\x1a\n")
else:
    print("skip real PNG: no converter on this machine")

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{len(fails)} failures" if fails else "\nelectricidad_plan_selftest: all ok")
sys.exit(1 if fails else 0)
