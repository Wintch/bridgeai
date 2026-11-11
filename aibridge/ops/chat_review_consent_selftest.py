#!/usr/bin/env python3
"""Offline checks that ops/chat_review.py obeys the person's /compartir choice. Run: python3 -I ops/chat_review_consent_selftest.py"""
import json, os, sqlite3, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
db, w = f"{tmp}/state.db", f"{tmp}/w"
os.makedirs(w)
c = sqlite3.connect(db)
c.execute("create table messages (id integer primary key, session_id text, role text, content text, tool_calls text, timestamp real, active integer default 1)")
now = time.time()
c.execute("insert into messages (session_id, role, content, tool_calls, timestamp) values ('s1','user','SECRETO-DEL-USUARIO hola',null,?)", (now - 60,))
c.execute("insert into messages (session_id, role, content, tool_calls, timestamp) values ('s1','assistant','RESPUESTA-VISIBLE',null,?)", (now - 50,))
c.commit(); c.close()
fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)


def review(*extra, level=None):
    p = f"{w}/.compartir.json"
    if os.path.exists(p): os.unlink(p)
    if level: json.dump({"level": level}, open(p, "w"))
    r = subprocess.run([sys.executable, "-I", f"{HERE}/chat_review.py", "--db", db, "--workdir", w, "--hours", "1", *extra], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


rc, out = review(level="nada")
check("nada: nothing is reviewed, not even the structure", rc == 0 and "no se revisa" in out and "SECRETO" not in out and "sesión" not in out)
rc, out = review("--mode", "text", level="nada")
check("nada: text mode refuses too", rc == 0 and "no se revisa" in out and "SECRETO" not in out)
rc, out = review(level="uso")
check("uso: the structure is shown, never the text", rc == 0 and "sesión" in out and "SECRETO" not in out and "RESPUESTA" not in out)
rc, out = review("--mode", "text", level="uso")
check("uso: text mode refuses and says what to ask for", rc == 0 and "SECRETO" not in out and "/compartir todo" in out)
rc, out = review("--mode", "text")
check("no choice file: still structure only, text refused", rc == 0 and "SECRETO" not in out and "/compartir todo" in out)
rc, out = review("--mode", "text", level="todo")
check("todo: the text is shown", rc == 0 and "SECRETO-DEL-USUARIO" in out and "RESPUESTA-VISIBLE" in out)
rc, out = review("--mode", "text", "--own")
check("--own (the operator's own stack) reads the text without a choice file", rc == 0 and "SECRETO-DEL-USUARIO" in out)
rc, out = review("--mode", "text", "--own", level="nada")
check("--own does not override a person who chose nada", rc == 0 and "SECRETO" not in out and "no se revisa" in out)
open(f"{w}/.compartir.json", "w").write("{broken")
rc, out = subprocess.run([sys.executable, "-I", f"{HERE}/chat_review.py", "--db", db, "--workdir", w, "--hours", "1"], capture_output=True, text=True).returncode, ""
check("a broken choice file means the default (uso): structure works", rc == 0)
print("\n".join(fails) or "chat_review_consent_selftest: all ok")
sys.exit(1 if fails else 0)
