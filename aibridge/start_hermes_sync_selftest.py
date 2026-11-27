#!/usr/bin/env python3
"""start_hermes.sh sync-out: an unchanged directory is not copied again, an empty -wal does not make a .db "newer", and the
periodic loop leaves logs out except every 20th round. python3 start_hermes_sync_selftest.py"""
import atexit, os, re, shutil, subprocess, sys, tempfile, time
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "start_hermes.sh")).read()
fails = []
tmp = tempfile.mkdtemp(prefix="shsync-selftest-"); atexit.register(shutil.rmtree, tmp, True)
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

def func(name):
    m = re.search(r"^%s\(\) \{.*\}\n" % re.escape(name), src, re.M)   # one-liner
    if not m: m = re.search(r"^%s\(\) \{[^\n]*\n.*?^\}\n" % re.escape(name), src, re.M | re.S)
    assert m, name
    return m.group(0)
defs = "".join(func(n) for n in ("sync_fail", "atomic_cp", "sync_path", "restore_ok", "sync_out_all"))
home, per, stamps = (os.path.join(tmp, d) for d in ("home", "persist", "stamps"))
for d in (home + "/.hermes/skills/a", home + "/.hermes/logs", per, stamps): os.makedirs(d, exist_ok=True)
def run(body):
    sh = (f'set -u\nHOME={home}; PERSIST_DIR={per}; SYNC_STAMP_DIR={stamps}; FRESH_CONTAINER=0; RESTORE_BAD=""\n'
          f'PERSIST_PATHS="kanban.db logs"\n{defs}\n{body}\n')
    return subprocess.run(["bash", "-c", sh], capture_output=True, text=True)
def w(p, t):
    os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(t)

# directories: copied once, skipped while unchanged, copied again after a change
w(home + "/.hermes/skills/a/SKILL.md", "v1")
run('sync_path "$HOME/.hermes/skills" "$PERSIST_DIR/skills"')
check("a directory is copied the first time", open(per + "/skills/a/SKILL.md").read() == "v1")
os.remove(per + "/skills/a/SKILL.md")   # a marker: a second copy would bring it back
time.sleep(1.1)
run('sync_path "$HOME/.hermes/skills" "$PERSIST_DIR/skills"')
check("an unchanged directory is not copied again", not os.path.exists(per + "/skills/a/SKILL.md"))
w(home + "/.hermes/skills/a/SKILL.md", "v2")
run('sync_path "$HOME/.hermes/skills" "$PERSIST_DIR/skills"')
check("a change in the directory is copied", open(per + "/skills/a/SKILL.md").read() == "v2")
os.remove(per + "/skills/a/SKILL.md"); time.sleep(1.1)
os.rename(home + "/.hermes/skills/a/SKILL.md", home + "/.hermes/skills/a/moved.md")
os.utime(home + "/.hermes/skills/a/moved.md", (1, 1))   # an old mtime, as cp -a or tar would leave
run('sync_path "$HOME/.hermes/skills" "$PERSIST_DIR/skills"')
check("a file moved in with an old mtime is still seen (ctime)", os.path.exists(per + "/skills/a/moved.md"))
r = run('sync_path "$HOME/.hermes/skills" "$PERSIST_DIR/skills"; ls "$SYNC_STAMP_DIR" | grep -c "\\.new$" || true')
check("no stamp is left half-made", r.stdout.strip() == "0")

# .db: an empty -wal newer than the copy does not trigger a copy; a non-empty one does
db = home + "/.hermes/kanban.db"
import sqlite3
c = sqlite3.connect(db); c.execute("CREATE TABLE t(x)"); c.execute("INSERT INTO t VALUES(1)"); c.commit(); c.close()
if True:   # without the sqlite3 CLI the copy falls back to a plain atomic cp: the "newer?" decision is the same
    run('sync_path "$HOME/.hermes/kanban.db" "$PERSIST_DIR/kanban.db"')
    m1 = os.stat(per + "/kanban.db").st_mtime_ns
    time.sleep(1.1); open(db + "-wal", "w").close()
    run('sync_path "$HOME/.hermes/kanban.db" "$PERSIST_DIR/kanban.db"')
    check("an empty -wal does not cause a copy", os.stat(per + "/kanban.db").st_mtime_ns == m1)
    time.sleep(1.1); w(db + "-wal", "x" * 100)
    os.utime(db, (1, 1))
    r = run('sync_path "$HOME/.hermes/kanban.db" "$PERSIST_DIR/kanban.db"')
    check("a non-empty newer -wal still causes a copy", os.stat(per + "/kanban.db").st_mtime_ns != m1)

# logs: left out when SYNC_SKIP names them, copied by a full sync
w(home + "/.hermes/logs/agent.log", "line\n")
run('SYNC_SKIP=logs sync_out_all')
check("SYNC_SKIP=logs leaves logs out", not os.path.exists(per + "/logs/agent.log"))
run('sync_out_all')
check("a full sync copies logs", os.path.exists(per + "/logs/agent.log"))
check("the loop syncs logs every 20th round only", "if [ $((n % 20)) = 0 ]; then sync_out_all; else SYNC_SKIP=logs sync_out_all; fi" in src)
check("the stop still runs a full sync_out_all", re.search(r"^  sync_out_all\n  echo \"\[start_hermes\] state flushed", src, re.M) is not None)
print("\n".join(fails) or "start_hermes_sync_selftest: all ok")
sys.exit(1 if fails else 0)
