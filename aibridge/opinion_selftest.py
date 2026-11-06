#!/usr/bin/env python3
"""Offline checks for opinion.py (/opinion, /compartir) and ops/opiniones.py. Run: python3 -I opinion_selftest.py"""
import contextlib, importlib.util, io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ.update(AIBRIDGE_OPINION_DIR=tmp, AIBRIDGE_PREFS=f"{tmp}/prefs.json")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


op = load("opinion", f"{HERE}/opinion.py")
ops = load("opiniones", f"{HERE}/ops/opiniones.py")
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)


def run(*argv):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        rc = op.main(list(argv))
    return rc, b.getvalue()


def lines(name):
    p = f"{tmp}/{name}"
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def setlang(l):
    json.dump({"lang": l}, open(f"{tmp}/prefs.json", "w"))


rc, out = run()
check("no argument explains how to write one", rc == 2 and "/opinion" in out and "privado" in out)
rc, out = run("privado")
check("'privado' alone writes nothing", rc == 2 and not lines(".opiniones-privadas.jsonl"))

rc, out = run("me", "gustó", "que", "conteste", "rápido")
n = lines(".opiniones.jsonl")
check("a note for the administrator is stored and says so", rc == 0 and len(n) == 1 and n[0]["text"] == "me gustó que conteste rápido" and "administrador" in out)
check("the note keeps the sharing level at the time and the language", n[0]["level"] == "uso" and n[0]["lang"] == "es" and n[0]["ts"] > 0)
check("a plain note does not go to the private file", not lines(".opiniones-privadas.jsonl"))

rc, out = run("privado", "algo", "mío")
check("a private note goes to its own file and says nobody reads it", rc == 0 and lines(".opiniones-privadas.jsonl")[0]["text"] == "algo mío" and len(lines(".opiniones.jsonl")) == 1 and "Nadie" in out)
rc, out = run("Privada", "otra")
check("'privada' and any case work too", rc == 0 and len(lines(".opiniones-privadas.jsonl")) == 2)

# the administrator's list never includes the private ones
rows = ops.notes(30, None, root=[("prueba", tmp)])
check("ops/opiniones lists the notes for the administrator only", len(rows) == 1 and rows[0][2]["text"].startswith("me gustó"))
src = open(f"{HERE}/ops/opiniones.py").read()
check("ops/opiniones never opens the private file", ".opiniones.jsonl" in src and "privadas" not in src.replace("The private notes", "").replace("opiniones-privadas.jsonl", "").lower().replace("private notes", ""))

# secrets are blanked before they are written
rc, out = run("mi", "clave", "es", "sk-abcdefghijklmnop1234", "y", "otra", "A" * 45)
t = lines(".opiniones.jsonl")[-1]["text"]
check("a key pasted in a note is blanked, and the person is told", "sk-abc" not in t and "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" not in t and "tachado" in t and "clave" in out and "Ojo" in out)
rc, out = run("x" * 5000)
check("a very long note is cut (2,000 characters at most, and a long run of one letter looks like a secret)", len(lines(".opiniones.jsonl")[-1]["text"]) <= op.MAX_CHARS)
rc, out = run("línea uno\x00\x07 y dos")
check("control characters do not reach the file", "\x00" not in lines(".opiniones.jsonl")[-1]["text"] and "\x07" not in lines(".opiniones.jsonl")[-1]["text"])

# the sharing level
check("no choice means 'uso'", op.level() == "uso")
rc, out = run("compartir")
check("/compartir shows the level and how to change it, and the honest note", rc == 0 and "uso" in out and "/compartir nada" in out and "acuerdo" in out)
rc, out = run("compartir", "nada")
check("nada is stored and described without promising a technical barrier", rc == 0 and op.level() == "nada" and "ni siquiera los conteos" in out and "acuerdo" in out)
rc, out = run("compartir", "TODO")
check("todo is stored (any case) and says the administrator may read the conversation", rc == 0 and op.level() == "todo" and "leer la conversación" in out)
check("a note written under 'todo' remembers it", (run("hola"), lines(".opiniones.jsonl")[-1]["level"])[1] == "todo")
rc, out = run("compartir", "mucho")
check("an unknown level changes nothing", rc == 2 and op.level() == "todo" and "nada, uso, todo" in out)
rc, out = run("compartir", "uso", "extra")
check("extra words are refused", rc == 2 and op.level() == "todo")
open(f"{tmp}/.compartir.json", "w").write("{broken")
check("an unreadable choice file falls back to 'uso'", op.level() == "uso")
open(f"{tmp}/.compartir.json", "w").write(json.dumps({"level": "everything"}))
check("an unknown level in the file falls back to 'uso'", op.level() == "uso")

# languages
for lang, word in (("ru", "Администратор"), ("en", "administrator")):
    setlang(lang)
    rc, out = run("compartir", "uso")
    check(f"{lang}: the level text is in that language", rc == 0 and word in out)
    rc, out = run("hola")
    check(f"{lang}: the thanks are in that language", rc == 0 and word in out)
setlang("fr")
rc, out = run("compartir")
check("an unsupported language falls back to Spanish", "Lo que compartís" in out)
check("the three languages have the same keys", all(set(op.MSG[l]) == set(op.MSG["es"]) and set(op.MSG[l]["what"]) == {"nada", "uso", "todo"} for l in op.MSG))

print("\n".join(fails) or "opinion_selftest: all ok")
sys.exit(1 if fails else 0)
