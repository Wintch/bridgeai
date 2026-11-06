#!/usr/bin/env python3
"""Offline checks for manual.py and the three manuals in manual/. Run: python3 -I manual_selftest.py"""
import contextlib, importlib.util, io, json, os, re, stat, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.makedirs(f"{tmp}/bin")
os.environ.update(AIBRIDGE_MANUAL_DIR=f"{HERE}/manual", AIBRIDGE_MANUAL_OUT=f"{tmp}/out", AIBRIDGE_PREFS=f"{tmp}/prefs.json")
spec = importlib.util.spec_from_file_location("manual", f"{HERE}/manual.py")
mn = importlib.util.module_from_spec(spec); spec.loader.exec_module(mn)
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)


def run(*argv):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        rc = mn.main(list(argv))
    return rc, b.getvalue()


def fake_pandoc(ok=True):
    p = f"{tmp}/bin/pandoc"
    open(p, "w").write("#!/bin/sh\nout=\nwhile [ $# -gt 0 ]; do [ \"$1\" = -o ] && out=$2; shift; done\n" + ('printf %%PDF-fake > "$out"\n' if ok else "echo boom >&2; exit 1\n"))
    os.chmod(p, 0o755)
    os.environ["PATH"] = f"{tmp}/bin:" + os.environ.get("PATH", "")


texts = {l: open(f"{HERE}/manual/MANUAL.{l}.md", encoding="utf-8").read() for l in ("es", "ru", "en")}

# the manuals themselves
h2 = {l: re.findall(r"^## .*", t, re.M) for l, t in texts.items()}
check("the three manuals have the same number of sections", len({len(v) for v in h2.values()}) == 1 and len(h2["es"]) >= 7)
check("each starts with a title", all(t.lstrip().startswith("# ") for t in texts.values()))
words = {l: len(t.split()) for l, t in texts.items()}
check(f"each is about 2 to 3 printed pages ({words})", all(800 <= w <= 1400 for w in words.values()))
ayuda_src = open(f"{HERE}/gateway.py", encoding="utf-8").read()
plug_src = open(f"{HERE}/hermes_plugins/aibridge-controls/__init__.py", encoding="utf-8").read()
builtin = {"commands", "stop", "new", "retry", "undo", "model", "btw"}
known = {c for c in re.findall(r'"([a-z]+)":\s*\(', ayuda_src)} | {c for c in re.findall(r'\("([a-z]+)", cmd_', plug_src)} | builtin
for l, t in texts.items():
    used = set(re.findall(r"(?<![\w/])/([a-z]{3,})\b", re.sub(r"https?://\S+", "", t)))
    check(f"{l}: every /command it mentions exists ({sorted(used - known) or 'none unknown'})", used <= known | {"workdir"})
    check(f"{l}: it documents the sharing choice and the three levels", all(w in t for w in ("/compartir", "nada", "uso", "todo", "/opinion")))
    check(f"{l}: it never promises that nobody, not even the administrator, can see the keys", not re.search(r"ни администратор|not even the administrator|ni el administrador", t, re.I))
packs = json.load(open(f"{HERE}/skill_packs.json"))
packs = packs.get("packs", packs)
ids = [p["id"] if isinstance(p, dict) and "id" in p else p for p in (packs if isinstance(packs, list) else packs.keys())]
check("every pack id of the catalog appears in the Spanish manual", all(i in texts["es"] for i in ids if i != "base"))

# manual.py
rc, out = run("es")
check("the short guide lists every section's heading", rc == 0 and out.count("•") == len(h2["es"]) and out.startswith("📖"))
fake_pandoc(False)
rc, out = run("es")
check("without a PDF the text still answers and says so", rc == 0 and "MEDIA:" not in out and "No pude armar el PDF" in out)
rc, out = run("--pdf", "es")
check("--pdf that cannot build says so and fails", rc == 1 and "MEDIA:" not in out)
fake_pandoc(True)
rc, out = run("--pdf", "ru")
pdf = f"{tmp}/out/Hermes-manual-ru.pdf"
check("--pdf builds the file and prints a MEDIA: line with its path", rc == 0 and out.strip().splitlines()[-1] == f"MEDIA:{pdf}" and os.path.getsize(pdf) > 0 and not os.path.exists(pdf + ".tmp.pdf"))
m1 = os.path.getmtime(pdf)
os.utime(pdf, (m1 + 100, m1 + 100))
rc, out = run("--pdf", "ru")
check("the PDF is not rebuilt while the text is unchanged", os.path.getmtime(pdf) == m1 + 100)
os.utime(pdf, (1, 1))
run("--pdf", "ru")
check("it is rebuilt when the manual is newer", os.path.getmtime(pdf) > 1000)
rc, out = run("completo", "en")
check("'completo' prints the whole manual in the asked language", rc == 0 and out.startswith("# Your Hermes") )
json.dump({"lang": "ru"}, open(f"{tmp}/prefs.json", "w"))
rc, out = run()
check("no argument follows the person's /idioma", "Руководство" in out or "руководство" in out)
json.dump({"lang": "xx"}, open(f"{tmp}/prefs.json", "w"))
rc, out = run("--full")
check("an unknown language falls back to Spanish", out.startswith("# Tu Hermes"))
mn.DIR = f"{tmp}/none"
rc, out = run("es")
check("a missing manual is reported", rc == 1 and "No encuentro" in out)

print("\n".join(fails) or "manual_selftest: all ok")
sys.exit(1 if fails else 0)
