#!/usr/bin/env python3
"""Offline checks that ops/chat_review.py counts failed tool results by exit code and cause, not by the word "error".
Run: python3 -I ops/chat_review_errors_selftest.py"""
import importlib.util, json, os, sqlite3, subprocess, sys, tempfile, time
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("cr", os.path.join(HERE, "chat_review.py"))
cr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr)
fails = []


def check(name, got, want=True):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   got {got!r}, want {want!r}"))
    if not ok: fails.append(name)


def term(code, out="", err=None):
    return json.dumps({"output": out, "exit_code": code, "error": err})


check("exit code 0 with 'errors' in the log is fine", cr.error_kind(term(0, "subs-fetch: 0 new subtitles, 11 in total; 0 errors")), None)
check("exit code 0 whatever the output says", cr.error_kind(term(0, "Traceback (most recent call last) was only quoted")), None)
check("a job started in the background (no exit code yet) is fine", cr.error_kind(term(None, "started")), None)
check("exit code 2 is a failure, the cause comes from the words", cr.error_kind(term(2, "usage: subs-fetch [-h]")), "other")
check("exit code 1 with a timeout", cr.error_kind(term(1, "curl: (28) Operation timed out")), "timeout")
check("exit code 127 with a missing file", cr.error_kind(term(127, "bash: x.sh: No such file or directory")), "not found")
check("exit code 1 with a refusal", cr.error_kind(term(1, "Permission denied (publickey)")), "denied")
check("exit code 75 with a rate limit", cr.error_kind(term(75, "RATE LIMITED by the site")), "rate limit")
check("an error field with a zero exit code is a failure", cr.error_kind(term(0, "", "tool crashed with Traceback")), "traceback")
check("plain text: 'no errors' is not an error", cr.error_kind("Done: 12 files, no errors."), None)
check("plain text: 'errors: 0' is not an error", cr.error_kind("summary errors: 0"), None)
check("plain text: a real error is found with its cause", cr.error_kind("Error: connection timed out after 30 s"), "timeout")
check("plain text: a Traceback", cr.error_kind("Traceback (most recent call last):\n  File x"), "traceback")
check("plain text without any error word", cr.error_kind("all fine, 3 files written"), None)
check("another tool's JSON without an error field falls back to the words", cr.error_kind(json.dumps({"results": ["x"]})), None)

# End to end: the summary prints the count and the causes, never the text.
tmp = tempfile.mkdtemp()
db, w = f"{tmp}/state.db", f"{tmp}/w"
os.makedirs(w)
c = sqlite3.connect(db)
c.execute("create table messages (id integer primary key, session_id text, role text, content text, tool_calls text, timestamp real, active integer default 1)")
now = time.time()
rows = [("user", "hola", None), ("assistant", "", json.dumps([{"function": {"name": "terminal"}}] * 3)),
        ("tool", term(0, "0 errors"), None), ("tool", term(1, "Permission denied SECRETO"), None), ("tool", term(1, "timed out"), None),
        ("assistant", "listo", None)]
for i, (role, content, tc) in enumerate(rows):
    c.execute("insert into messages (session_id, role, content, tool_calls, timestamp) values ('s1',?,?,?,?)", (role, content, tc, now - 100 + i))
c.commit(); c.close()
r = subprocess.run([sys.executable, "-I", f"{HERE}/chat_review.py", "--db", db, "--workdir", w, "--hours", "1"], capture_output=True, text=True)
out = r.stdout + r.stderr
check("summary: 3 results, 2 failures", "tool results: 3" in out and "tool results that look like errors: 2" in out, True)
check("summary: the causes are listed", "tool errors by cause: denied 1, timeout 1" in out or "tool errors by cause: timeout 1, denied 1" in out, True)
check("the structure mode shows no text", "SECRETO" not in out, True)
print("\n".join(fails) or "chat_review_errors_selftest: all ok")
sys.exit(1 if fails else 0)
