#!/usr/bin/env python3
"""Self-test for patches/admission_auto_resume.py on stand-ins of the three Hermes files it patches (each anchor verbatim) and a
sqlite stand-in of the admission store (the SQL the patch runs, with the upstream functions it calls reduced to what they
do to these tables). The real files are checked at image build time (the patch aborts unless each anchor matches once)
and against the v0.23.1 code in staging.
Run: python3 -I admission_auto_resume_selftest.py
"""
import asyncio
import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


UNKNOWN = '''"""stand-in"""
from __future__ import annotations

import logging

from hermes_state_keys import CRON_PRINCIPAL_ID

logger = logging.getLogger(__name__)


def is_unattended(row) -> bool:
    principal = row.get('principal_id') or ''
    if principal == CRON_PRINCIPAL_ID or principal.startswith('automation:'):
        return True
    payload = row.get('payload') or {}
    native = payload.get('native_text_v1') or {}
    return ('local_automation_v1' in payload or 'kanban_card_v1' in payload
            or 'automation' in native or 'webhook_delivery' in native)


def _unattended_unknown(rows):
    return [row for row in rows if row['status'] == 'unknown' and is_unattended(row)]


def settle_recovered_unattended(db, epoch) -> int:
    settled = 0
    for row in []:
        settled += 1
        logger.info('Lost automation admission %s on session %s settled interrupted (not replayed)',
                    row['admission_id'], row['target_session_id'])
    return settled


async def settle_unattended_unknown(authority, ref) -> bool:
    import asyncio

    from agent.turn_failure_copy import AUTOMATION_INTERRUPTED_NOTICE
    from hermes_state_runtime import RuntimeStoreError, list_session_admissions
    rows = await asyncio.to_thread(list_session_admissions, authority.db, session_id=ref.session_id)
    settled = False
    for row in _unattended_unknown(rows):
        settled = True
    return settled
'''
INGRESS = '''import asyncio


async def execute_admission(authority, ref, row):
    event = authority.event
    # The claim passed the admission gate, which refuses once a drain begins.
    event._admitted_before_drain = event.internal is True
    return event
'''
AUTHORITIES = '''def holds_admission(authority, session_id) -> bool:
    try:
        return bool(authority.db._read_one(
            'SELECT 1 FROM session_admissions WHERE target_session_id IN (?,?) LIMIT 1',
            (session_id, session_id)))
    except Exception:
        return True
'''

d = tempfile.mkdtemp()
paths = {}
for name, text in (("session_unattended_unknown.py", UNKNOWN), ("session_ingress.py", INGRESS),
                   ("session_authorities.py", AUTHORITIES)):
    paths[name] = os.path.join(d, name)
    open(paths[name], "w").write(text)
patch = os.path.join(HERE, "patches", "admission_auto_resume.py")
args = [sys.executable, patch, paths["session_unattended_unknown.py"], paths["session_ingress.py"],
        paths["session_authorities.py"]]
r1 = subprocess.run(args, capture_output=True, text=True)
r2 = subprocess.run(args, capture_output=True, text=True)
check("the patch applies to the three stand-ins", r1.returncode == 0 and r1.stdout.count("patched:") == 3, r1.stdout + r1.stderr)
check("a second run is a no-op", r2.returncode == 0 and r2.stdout.count("already patched") == 3, r2.stdout + r2.stderr)
for name in paths:
    check("py_compile " + name, subprocess.run([sys.executable, "-m", "py_compile", paths[name]]).returncode == 0)

# A file that misses an anchor aborts and leaves the others untouched.
e = tempfile.mkdtemp()
ep = {n: os.path.join(e, n) for n in paths}
open(ep["session_unattended_unknown.py"], "w").write(UNKNOWN)
open(ep["session_ingress.py"], "w").write("async def execute_admission():\n    pass\n")
open(ep["session_authorities.py"], "w").write(AUTHORITIES)
r3 = subprocess.run([sys.executable, patch, *ep.values()], capture_output=True, text=True)
check("a missing anchor aborts the build", r3.returncode != 0 and "patch failed" in (r3.stdout + r3.stderr), r3.stdout + r3.stderr)
check("...and writes nothing", open(ep["session_unattended_unknown.py"]).read() == UNKNOWN
      and open(ep["session_authorities.py"]).read() == AUTHORITIES)
check("no temp file is left behind", not [f for f in os.listdir(e) if f.endswith(".aibridge-tmp")])
src_ing = open(paths["session_ingress.py"]).read()
check("the replay note goes in before the event is used", src_ing.index("replay_note_for") < src_ing.index("_admitted_before_drain"))
check("holds_admission counts unsettled work only", "status IN ('queued','started','unknown')" in open(paths["session_authorities.py"]).read())

# ---- behaviour of the patched session_unattended_unknown against a sqlite stand-in of the store ----
conn = sqlite3.connect(":memory:", check_same_thread=False)
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE session_admissions (seq INTEGER PRIMARY KEY AUTOINCREMENT, admission_id TEXT UNIQUE, request_id TEXT,
  principal_id TEXT, target_session_id TEXT, lineage_json TEXT, payload_json TEXT, payload_digest TEXT, intent TEXT,
  status TEXT, outcome TEXT, owner_epoch INTEGER, generation INTEGER, retired_at REAL);
CREATE TABLE state_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, content TEXT, timestamp REAL);
CREATE TABLE sessions (id TEXT PRIMARY KEY, runtime_revision INTEGER DEFAULT 0);
CREATE TABLE worker_executions (execution_id TEXT, session_id TEXT, generation INTEGER, owner_epoch INTEGER, status TEXT);
""")
EPOCH = [2]


class RuntimeStoreError(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class DB:
    @contextlib.contextmanager
    def _read_ctx(self):
        yield conn

    def _execute_write(self, fn):
        out = fn(conn)
        conn.commit()
        return out


def _row(r):
    if r is None:
        return None
    out = dict(r)
    out["payload"] = json.loads(out.pop("payload_json"))
    for k in ("payload_digest", "lineage_json", "retired_at"):
        out.pop(k, None)
    return out


def _admission(c, aid):
    r = c.execute("SELECT * FROM session_admissions WHERE admission_id=?", (aid,)).fetchone()
    if r is None:
        raise RuntimeStoreError("not_found")
    return r


def _epoch(c, epoch):
    if epoch != EPOCH[0]:
        raise RuntimeStoreError("stale_epoch")


def _retire(c, raw, owner_epoch):
    c.execute("UPDATE worker_executions SET status='terminal' WHERE session_id=? AND generation=? AND owner_epoch=?",
              (raw["target_session_id"], raw["generation"], owner_epoch))


def resolve(db, *, epoch, admission_id, generation, _terminal_write=None):
    def write(c):
        _epoch(c, epoch)
        raw = _admission(c, admission_id)
        if raw["status"] != "unknown" or raw["generation"] != generation:
            raise RuntimeStoreError("stale_generation")
        if _terminal_write:
            _terminal_write(c, _row(raw))
        c.execute("UPDATE session_admissions SET status='terminal',outcome='interrupted' WHERE admission_id=?", (admission_id,))
    return db._execute_write(write)


def close_discarded_turn(db, c, row, notice=None):
    c.execute("INSERT INTO messages(session_id,role,content,timestamp) VALUES(?,?,?,?)",
              (row["target_session_id"], "assistant", notice or "DEFAULT-NOTICE", time.time()))


def stub(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


FRESH = [3600.0]
released = []
stub("hermes_state_keys", CRON_PRINCIPAL_ID="cron")
def list_session_admissions(db, *, session_id, pending_only=True):
    return [_row(r) for r in conn.execute("SELECT * FROM session_admissions WHERE target_session_id=? AND status IN "
                                          "('queued','started','unknown') ORDER BY seq", (session_id,))]


stub("hermes_state_runtime", list_session_admissions=list_session_admissions, RuntimeStoreError=RuntimeStoreError, _row=_row, _admission=_admission, _epoch=_epoch,
     _retire_admission_workers=_retire, resolve_unknown_session_input=resolve, _canonical_chain=lambda c, s: [s])
stub("hermes_state_local_lineage", local_physical_target=lambda c, s: s)
for pkg in ("gateway", "agent"):
    stub(pkg).__path__ = []
stub("agent.turn_failure_copy", AUTOMATION_INTERRUPTED_NOTICE="AUTO")
stub("gateway.session_results", close_discarded_turn=close_discarded_turn)
stub("gateway.session_ingress_media", release_admission_media=lambda db, aid: released.append(aid))
stub("gateway.session_lifecycle", auto_continue_freshness_window=lambda: FRESH[0])
mod = types.ModuleType("sun")
exec(compile(open(paths["session_unattended_unknown.py"]).read(), "sun.py", "exec"), mod.__dict__)
db = DB()


def add(sid, payload, status="unknown", principal="tg:1", owner_epoch=1, generation=5, text_age=10):
    conn.execute("INSERT OR IGNORE INTO sessions(id) VALUES(?)", (sid,))
    conn.execute("INSERT INTO messages(session_id,role,content,timestamp) VALUES(?,?,?,?)",
                 (sid, "user", "x", time.time() - text_age))
    aid = "a%d" % (conn.execute("SELECT COUNT(*) FROM session_admissions").fetchone()[0] + 1)
    conn.execute("INSERT INTO session_admissions(admission_id,request_id,principal_id,target_session_id,lineage_json,payload_json,"
                 "payload_digest,intent,status,owner_epoch,generation) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                 (aid, aid, principal, sid, "[]", json.dumps(payload), "d", "queue", status, owner_epoch, generation))
    conn.commit()
    return aid


def st(aid):
    r = conn.execute("SELECT status,outcome,generation FROM session_admissions WHERE admission_id=?", (aid,)).fetchone()
    return (r[0], r[1])


native = add("s1", {"text": "do it", "native_text_v1": {}})
later = add("s1", {"text": "next", "native_text_v1": {}}, status="queued", owner_epoch=2, generation=None)
api = add("s2", {"text": "hi", "api_turn_v1": {}}, principal="api")
viewer = add("s3", {"text": "v"}, principal="viewer")
auto = add("s4", {"text": "cron", "local_automation_v1": {}}, principal="cron")
stale = add("s5", {"text": "old", "native_text_v1": {}}, text_age=7200)
same_epoch = add("s6", {"text": "lost this run", "native_text_v1": {}}, owner_epoch=2)
conn.execute("INSERT INTO worker_executions VALUES('w','s1',5,1,'unknown')")
conn.commit()
done = mod.settle_recovered_unattended(db, 2)
check("a person's chat turn goes back to queued", st(native) == ("queued", None), st(native))
check("its generation is cleared and the replay marker is written",
      conn.execute("SELECT generation FROM session_admissions WHERE admission_id=?", (native,)).fetchone()[0] is None
      and mod.replay_note_for(db, native) == mod.REPLAY_NOTE)
check("the note is the neutral English sentence", mod.REPLAY_NOTE == "[SYSTEM: this turn was interrupted by a restart; "
      "check what was already done before repeating any action]")
check("the worker row it owned is retired, so the FIFO is not blocked",
      conn.execute("SELECT status FROM worker_executions").fetchone()[0] == "terminal")
check("it keeps its FIFO place (before the message queued behind it)",
      conn.execute("SELECT admission_id FROM session_admissions WHERE target_session_id='s1' AND status='queued' ORDER BY seq").fetchone()[0] == native)
check("a message queued behind it is untouched and has no note", st(later) == ("queued", None) and mod.replay_note_for(db, later) is None)
check("an API turn settles interrupted with the transcript boundary, media released",
      st(api) == ("terminal", "interrupted") and api in released
      and conn.execute("SELECT content FROM messages WHERE session_id='s2' AND role='assistant'").fetchone()[0] == "DEFAULT-NOTICE")
check("a viewer's turn keeps upstream's pause", st(viewer) == ("unknown", None))
check("an automation turn is left to upstream's own settle", st(auto) == ("unknown", None))
check("a turn older than the freshness window keeps the pause", st(stale) == ("unknown", None))
check("an unknown of this same epoch (a lost worker of this process) keeps the pause", st(same_epoch) == ("unknown", None))
FRESH[0] = 0
check("a non-positive window disables the freshness gate", mod.auto_resume_unknown(db, 2)["requeued"][0]["admission_id"] == stale)
FRESH[0] = 3600.0

# Replayed once, claimed again, lost again: never a third run (only this session's row is left in the store).
conn.execute("DELETE FROM session_admissions WHERE target_session_id!='s1'")
conn.execute("UPDATE session_admissions SET status='queued' WHERE admission_id=?", (later,))
conn.execute("UPDATE session_admissions SET status='unknown',generation=9,owner_epoch=2 WHERE admission_id=?", (native,))
conn.commit()
EPOCH[0] = 3
again = mod.auto_resume_unknown(db, 3)
check("a second loss is reported as `twice`, not requeued", [r["admission_id"] for r in again["twice"]] == [native]
      and not again["requeued"] and st(native) == ("unknown", None), again)


class Source:
    chat_id = "1001"
    platform = "telegram"


class Live:
    source = Source()


sent = []


class Adapter:
    async def send(self, chat_id, text, metadata=None):
        sent.append((chat_id, text))


class Runner:
    def _delivery_adapter_for(self, source):
        return Adapter()

    def _thread_metadata_for_source(self, source):
        return {}


class Auth:
    db = DB()
    epoch = 3
    sessions = {"s1": Live()}
    runner = Runner()

    async def resolve_unknown_as_owner(self, ref, aid, generation, notice=None):
        return resolve(self.db, epoch=3, admission_id=aid, generation=generation,
                       _terminal_write=lambda c, lost: close_discarded_turn(self.db, c, lost, notice))


stub("gateway.run", _interim_metadata=lambda m: dict(m or {}, interim=True),
     _non_conversational_metadata=lambda m, platform=None: m)
ref = types.SimpleNamespace(session_id="s1")
ok = asyncio.run(mod.settle_unattended_unknown(Auth(), ref))
check("the drain settles the twice-lost turn so the queue moves", ok is True and st(native) == ("terminal", "interrupted"), st(native))
check("its transcript carries the notice", conn.execute("SELECT content FROM messages WHERE session_id='s1' AND role='assistant'").fetchone()[0]
      == mod.REPLAY_TWICE_NOTICE)
check("the person gets exactly one English line", sent == [("1001", mod.REPLAY_TWICE_TO_PERSON)], sent)
check("a second drain finds nothing to do", asyncio.run(mod.settle_unattended_unknown(Auth(), ref)) is False)

print()
if fails:
    print("%d FAILED: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("all admission_auto_resume checks passed")
