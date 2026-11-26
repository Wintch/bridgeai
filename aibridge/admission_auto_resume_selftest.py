#!/usr/bin/env python3
"""Self-test for patches/admission_auto_resume.py on stand-ins of the five Hermes files it patches (each anchor verbatim) and a
sqlite stand-in of the admission store (the SQL the patch runs, with the upstream functions it calls reduced to what they
do to these tables). The stand-ins follow v0.23.4's persistence layer: the store is a storage interface handle whose
repositories reach SQLite through `admissions._store.holder()`. The real files are checked at image build time (the patch
aborts unless each anchor matches once); admission_auto_resume_realcode_test.py runs the real boot sequence.
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

from persistence.authority.vocabulary import CRON_PRINCIPAL_ID

logger = logging.getLogger(__name__)


def is_unattended(row) -> bool:
    principal = row.get('principal_id') or ''
    if principal == CRON_PRINCIPAL_ID or principal.startswith('automation:'):
        return True
    payload = row.get('payload') or {}
    native = payload.get('native_text_v1') or {}
    return ('local_automation_v1' in payload or 'kanban_card_v1' in payload
            or 'automation' in native or 'webhook_delivery' in native)


def _unattended_unknown(records):
    from gateway.session_authority import admission_row
    return [row for row in map(admission_row, records) if row['status'] == 'unknown' and is_unattended(row)]


def settle_recovered_unattended(store, epoch) -> int:
    settled = 0
    for row in []:
        settled += 1
        logger.info('Lost automation admission %s on session %s settled interrupted (not replayed)',
                    row['admission_id'], row['target_session_id'])
    return settled


async def settle_unattended_unknown(authority, ref) -> bool:
    import asyncio

    from agent.turn_failure_copy import AUTOMATION_INTERRUPTED_NOTICE
    from gateway.session_persistence import authority_persistence
    from persistence.core.errors import AuthorityRefusal
    rows = await asyncio.to_thread(authority_persistence(authority).admissions.list, session_id=ref.session_id)
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
AUTHORITIES = '''def admission_owner(authority, session_id):
    return session_id


def holds_admission(authority, session_id) -> bool:
    from gateway.session_persistence import authority_persistence
    try:
        return authority_persistence(authority).admissions.has_pending(
            session_ids=(session_id, admission_owner(authority, session_id)))
    except Exception:
        return True
'''

RUNNER = '''class TurnRunner:
    def prep(self, ctx, resume_pending, interruption_is_fresh, mark_is_fresh, agent_history):
        if resume_pending and (interruption_is_fresh or mark_is_fresh):
            ctx.message = "STOCK-RESUME-NOTE\\n\\n" + ctx.message
        elif agent_history and agent_history[-1].get("role") == "tool" and interruption_is_fresh:
            ctx.message = "STOCK-TOOL-TAIL-NOTE\\n\\n" + ctx.message
        return ctx.message
'''

RUNTIME = '''import contextlib


def release_unknown_turn_markers(runner):
    store = getattr(runner, 'session_store', None)
    for authority in runner.authorities:
        with contextlib.nullcontext():
            if (persistence := authority.persistence) is None:
                raise RuntimeError('no storage handle')
            unknown = persistence.admissions.pending_targets(statuses=frozenset({'unknown'}))
            if not unknown:
                continue
            for entry in store.list_sessions():
                if entry.active_turn_token and entry.session_id in unknown:
                    store.clear_turn_active(entry.session_key, entry.active_turn_token)
'''

d = tempfile.mkdtemp()
paths = {}
for name, text in (("session_unattended_unknown.py", UNKNOWN), ("session_ingress.py", INGRESS),
                   ("session_authorities.py", AUTHORITIES), ("run_turn_runner.py", RUNNER),
                   ("run_runtime.py", RUNTIME)):
    paths[name] = os.path.join(d, name)
    open(paths[name], "w").write(text)
patch = os.path.join(HERE, "patches", "admission_auto_resume.py")
args = [sys.executable, patch, paths["session_unattended_unknown.py"], paths["session_ingress.py"],
        paths["session_authorities.py"], paths["run_turn_runner.py"], paths["run_runtime.py"]]
r1 = subprocess.run(args, capture_output=True, text=True)
r2 = subprocess.run(args, capture_output=True, text=True)
check("the patch applies to the five stand-ins", r1.returncode == 0 and r1.stdout.count("patched:") == 5, r1.stdout + r1.stderr)
check("a second run is a no-op", r2.returncode == 0 and r2.stdout.count("already patched") == 5, r2.stdout + r2.stderr)
for name in paths:
    check("py_compile " + name, subprocess.run([sys.executable, "-m", "py_compile", paths[name]]).returncode == 0)

# A file that misses an anchor aborts and leaves the others untouched.
e = tempfile.mkdtemp()
ep = {n: os.path.join(e, n) for n in paths}
open(ep["session_unattended_unknown.py"], "w").write(UNKNOWN)
open(ep["session_ingress.py"], "w").write("async def execute_admission():\n    pass\n")
open(ep["session_authorities.py"], "w").write(AUTHORITIES)
open(ep["run_turn_runner.py"], "w").write(RUNNER)
open(ep["run_runtime.py"], "w").write(RUNTIME)
r3 = subprocess.run([sys.executable, patch, *ep.values()], capture_output=True, text=True)
check("a missing anchor aborts the build", r3.returncode != 0 and "patch failed" in (r3.stdout + r3.stderr), r3.stdout + r3.stderr)
check("...and writes nothing", open(ep["session_unattended_unknown.py"]).read() == UNKNOWN
      and open(ep["session_authorities.py"]).read() == AUTHORITIES and open(ep["run_turn_runner.py"]).read() == RUNNER)
open(ep["session_ingress.py"], "w").write(INGRESS)
open(ep["run_turn_runner.py"], "w").write("class TurnRunner:\n    def prep(self):\n        pass\n")
r3c = subprocess.run([sys.executable, patch, *ep.values()], capture_output=True, text=True)
check("a missing run_turn_runner anchor aborts too, and writes nothing", r3c.returncode != 0 and "patch failed" in (r3c.stdout + r3c.stderr)
      and open(ep["session_ingress.py"]).read() == INGRESS and open(ep["session_unattended_unknown.py"]).read() == UNKNOWN,
      r3c.stdout + r3c.stderr)
open(ep["run_turn_runner.py"], "w").write(RUNNER)
open(ep["run_runtime.py"], "w").write("def release_unknown_turn_markers(runner):\n    pass\n")
r3d = subprocess.run([sys.executable, patch, *ep.values()], capture_output=True, text=True)
check("a missing run_runtime anchor aborts too, and writes nothing", r3d.returncode != 0 and "patch failed" in (r3d.stdout + r3d.stderr)
      and open(ep["session_ingress.py"]).read() == INGRESS and open(ep["session_unattended_unknown.py"]).read() == UNKNOWN
      and open(ep["run_turn_runner.py"]).read() == RUNNER, r3d.stdout + r3d.stderr)
check("no temp file is left behind", not [f for f in os.listdir(e) if f.endswith(".aibridge-tmp")])
src_ing = open(paths["session_ingress.py"]).read()
check("the replay text goes in before the event is used", src_ing.index("replay_text_for") < src_ing.index("_admitted_before_drain"))
check("holds_admission counts unsettled work only", "statuses=frozenset({'queued', 'started', 'unknown'})" in open(paths["session_authorities.py"]).read())
_ha = types.ModuleType("ha")
exec(compile(open(paths["session_authorities.py"]).read(), "ha.py", "exec"), _ha.__dict__)

# ---- behaviour of the patched session_unattended_unknown against a sqlite stand-in of the store ----
conn = sqlite3.connect(":memory:", check_same_thread=False)
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE session_admissions (seq INTEGER PRIMARY KEY AUTOINCREMENT, admission_id TEXT UNIQUE, request_id TEXT,
  principal_id TEXT, target_session_id TEXT, lineage_json TEXT, payload_json TEXT, payload_digest TEXT, intent TEXT,
  status TEXT, outcome TEXT, owner_epoch INTEGER, generation INTEGER, retired_at REAL);
CREATE TABLE state_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, content TEXT, timestamp REAL,
  active INTEGER DEFAULT 1, tool_calls TEXT, tool_call_id TEXT);
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


class _SQLiteStore:
    def holder(self):
        return DB()


class Admissions:
    """The admission repository of a stand-in storage handle (v0.23.4): records are plain row dicts here."""
    _store = _SQLiteStore()

    def list_unknown(self):
        return [_row(r) for r in conn.execute("SELECT * FROM session_admissions WHERE status='unknown' ORDER BY seq")]

    def list(self, *, session_id):
        return list_session_admissions(DB(), session_id=session_id)

    def resolve_unknown(self, *, epoch, admission_id, generation, notice=None, captured=None):
        return resolve(DB(), epoch=epoch, admission_id=admission_id, generation=generation,
                       _terminal_write=lambda c, lost: close_discarded_turn(None, c, lost, notice))

    def pending_targets(self, *, statuses):
        return frozenset(r[0] for r in conn.execute(
            "SELECT DISTINCT target_session_id FROM session_admissions WHERE status IN (%s)" % ",".join("?" * len(statuses)),
            tuple(statuses)))

    def has_pending(self, *, session_ids=(), statuses=None):
        HAS_PENDING.append(statuses)
        return False


HAS_PENDING = []


class Store:
    def __init__(self):
        self.admissions = Admissions()


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
def list_session_admissions(db, *, session_id, pending_only=True):
    return [_row(r) for r in conn.execute("SELECT * FROM session_admissions WHERE target_session_id=? AND status IN "
                                          "('queued','started','unknown') ORDER BY seq", (session_id,))]


for pkg in ("gateway", "agent", "persistence", "persistence.core", "persistence.authority", "persistence.sqlite",
            "persistence.sqlite.authority"):
    stub(pkg).__path__ = []
stub("persistence.authority.vocabulary", CRON_PRINCIPAL_ID="cron")
stub("persistence.core.errors", AuthorityRefusal=RuntimeStoreError)
stub("persistence.sqlite.authority._runtime", _admission=_admission, _epoch=_epoch, _retire_admission_workers=_retire,
     refused=contextlib.nullcontext)
stub("persistence.sqlite.authority._admission_store", _canonical_chain=lambda c, s: [s])
stub("persistence.sqlite.authority._local", local_physical_target=lambda c, s: s)
stub("gateway.session_authority", admission_row=lambda record: None if record is None else dict(record))
stub("gateway.session_persistence", authority_persistence=lambda authority: authority.persistence)
stub("agent.turn_failure_copy", AUTOMATION_INTERRUPTED_NOTICE="AUTO")
stub("gateway.session_results", close_discarded_turn=close_discarded_turn)
stub("gateway.session_ingress_media", release_admission_media=lambda db, aid: released.append(aid))
stub("gateway.session_lifecycle", auto_continue_freshness_window=lambda: FRESH[0])
mod = types.ModuleType("sun")
exec(compile(open(paths["session_unattended_unknown.py"]).read(), "sun.py", "exec"), mod.__dict__)
db = Store()   # the storage interface handle (v0.23.4); the name is kept from the v0.23.1 test
check("holds_admission asks for the unsettled statuses only",
      _ha.holds_admission(types.SimpleNamespace(persistence=db), "s0") is False
      and HAS_PENDING == [frozenset({"queued", "started", "unknown"})], HAS_PENDING)


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
      and mod.replay_text_for(db, native, "do it") == mod.REPLAY_NOTE + "\n\n" + "do it")
check("the note is the neutral English sentence", mod.REPLAY_NOTE == "[SYSTEM: this turn was interrupted by a restart; "
      "check what was already done before repeating any action]")
check("the worker row it owned is retired, so the FIFO is not blocked",
      conn.execute("SELECT status FROM worker_executions").fetchone()[0] == "terminal")
check("it keeps its FIFO place (before the message queued behind it)",
      conn.execute("SELECT admission_id FROM session_admissions WHERE target_session_id='s1' AND status='queued' ORDER BY seq").fetchone()[0] == native)
check("a message queued behind it is untouched and has no note", st(later) == ("queued", None) and mod.replay_text_for(db, later, "next") is None)
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
again = mod.auto_resume_unknown(db, 3, settle_twice=False)
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
    persistence = Store()
    epoch = 3
    sessions = {"s1": Live()}
    runner = Runner()

    async def resolve_unknown_as_owner(self, ref, aid, generation, notice=None):
        return self.persistence.admissions.resolve_unknown(epoch=3, admission_id=aid, generation=generation, notice=notice)


stub("gateway.run", _interim_metadata=lambda m: dict(m or {}, interim=True),
     _non_conversational_metadata=lambda m, platform=None: m)
ref = types.SimpleNamespace(session_id="s1")
ok = asyncio.run(mod.settle_unattended_unknown(Auth(), ref))
check("the drain settles the twice-lost turn so the queue moves", ok is True and st(native) == ("terminal", "interrupted"), st(native))
check("its transcript carries the notice", conn.execute("SELECT content FROM messages WHERE session_id='s1' AND role='assistant'").fetchone()[0]
      == mod.REPLAY_TWICE_NOTICE)
check("the person gets exactly one English line", sent == [("1001", mod.REPLAY_TWICE_TO_PERSON)], sent)
check("a second drain finds nothing to do", asyncio.run(mod.settle_unattended_unknown(Auth(), ref)) is False)


# ---- 1) boot: a twice-lost turn is settled at boot and the person is owed ONE line through the delivery ledger ----
import hashlib
import threading

ledger = sqlite3.connect(":memory:", check_same_thread=False)
ledger.execute("""CREATE TABLE delivery_obligations (obligation_id TEXT PRIMARY KEY, session_key TEXT NOT NULL, platform TEXT NOT NULL,
  chat_id TEXT NOT NULL, thread_id TEXT, content TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, owner_pid INTEGER, owner_started_at INTEGER, last_error TEXT, adapter_profile TEXT)""")
LEDGER_FAIL = [False]


def _obligation_write(fn):
    out = fn(ledger)
    ledger.commit()
    return out


@contextlib.contextmanager
def ledger_store():
    """delivery_ledger._store(): a storage handle whose coordination repository writes the obligations table (v0.23.4)."""
    if LEDGER_FAIL[0]:
        raise OSError("ledger db unavailable")
    yield types.SimpleNamespace(coordination=types.SimpleNamespace(_obligation_write=_obligation_write))


stub("gateway.delivery_ledger", _DB_LOCK=threading.Lock(), _store=ledger_store,
     compute_obligation_id=lambda session_key, message_ref, content:
     hashlib.sha256(f"{session_key}|{message_ref}|{content}".encode("utf-8", "replace")).hexdigest()[:24])
sys.modules["gateway"].delivery_ledger = sys.modules["gateway.delivery_ledger"]


def native_payload(text, chat="1001", thread=None, route="agent:main:telegram:dm:1001", profile=None):
    source = {"platform": "telegram", "chat_id": chat, "thread_id": thread}
    if profile:
        source["profile"] = profile
    return {"text": text, "native_text_v1": {"route": route, "source": source}}


def mark(aid):
    conn.execute("INSERT OR REPLACE INTO state_meta(key,value) VALUES(?,?)", (mod.REPLAY_META_PREFIX + aid, "2"))
    conn.commit()


EPOCH[0] = 4
conn.execute("DELETE FROM session_admissions")
conn.execute("DELETE FROM messages")
conn.execute("DELETE FROM state_meta")
conn.commit()
b1 = add("b1", native_payload("build the report"), generation=7)
mark(b1)
b2 = add("b2", native_payload("other chat", chat="2002", thread="9", route="agent:main:telegram:dm:2002"), generation=8)
mark(b2)
b3 = add("b3", native_payload("fresh loss"), generation=9)  # replayed never: boot requeues it, no notice owed
b4 = add("b4", native_payload("lost this process", route="agent:main:telegram:dm:3003"), owner_epoch=4, generation=3)
mark(b4)
released.clear()
mod.settle_recovered_unattended(db, 4)
check("boot settles a twice-lost turn interrupted (not requeued, not left paused)", st(b1) == ("terminal", "interrupted")
      and st(b2) == ("terminal", "interrupted"), (st(b1), st(b2)))
check("...with the transcript notice and its media released", conn.execute(
    "SELECT content FROM messages WHERE session_id='b1' AND role='assistant'").fetchone()[0] == mod.REPLAY_TWICE_NOTICE
    and b1 in released and b2 in released)
check("a turn lost for the first time is still requeued once", st(b3) == ("queued", None) and mod.replay_text_for(db, b3, "fresh loss") is not None)
check("a row of this same process keeps the pause", st(b4) == ("unknown", None))
rows = ledger.execute("SELECT session_key, platform, chat_id, thread_id, content, state, attempts, owner_pid, owner_started_at, adapter_profile "
                      "FROM delivery_obligations ORDER BY chat_id").fetchall()
check("exactly one owed line per chat, as an unowned pending row the boot sweep claims and sends plain",
      rows == [("agent:main:telegram:dm:1001", "telegram", "1001", None, mod.REPLAY_TWICE_TO_PERSON, "pending", 0, None, None, "default"),
               ("agent:main:telegram:dm:2002", "telegram", "2002", "9", mod.REPLAY_TWICE_TO_PERSON, "pending", 0, None, None, "default")], rows)
check("the line is short, English and tells the person what to do", len(mod.REPLAY_TWICE_TO_PERSON) < 160
      and "send it again" in mod.REPLAY_TWICE_TO_PERSON)
mod.settle_recovered_unattended(db, 4)
check("a second boot pass adds nothing (the row is settled; the ledger id is stable anyway)",
      ledger.execute("SELECT COUNT(*) FROM delivery_obligations").fetchone()[0] == 2)
ledger.execute("UPDATE delivery_obligations SET state='delivered'")
ledger.commit()
mod._owe_twice_notice([{"admission_id": b1, "payload": native_payload("build the report")}])
check("an already delivered line is never queued again (INSERT OR IGNORE)", ledger.execute(
    "SELECT COUNT(*) FROM delivery_obligations WHERE state!='delivered'").fetchone()[0] == 0)
ledger.execute("DELETE FROM delivery_obligations")
ledger.commit()
mod._owe_twice_notice([{"admission_id": "x1", "payload": native_payload("a")}, {"admission_id": "x2", "payload": native_payload("b")}])
check("several settled turns of one chat share one line", ledger.execute("SELECT content FROM delivery_obligations").fetchall()
      == [(mod.REPLAY_TWICE_TO_PERSON_MANY,)])
ledger.execute("DELETE FROM delivery_obligations")
ledger.commit()
b5 = add("b5", native_payload("ledger down"), generation=4)
mark(b5)
LEDGER_FAIL[0] = True
boot = mod.auto_resume_unknown_at_boot(db, 4)
LEDGER_FAIL[0] = False
check("a ledger failure never blocks the boot: the turn is still settled", boot is not None and st(b5) == ("terminal", "interrupted"), (boot, st(b5)))
check("the boot call records the sessions it settled (for the crash-marker release)", getattr(db, "aibridge_settled_at_boot", None) == {"b1", "b2", "b5"},
      getattr(db, "aibridge_settled_at_boot", None))

# ---- 1b) the marker of a turn settled at boot is released, so the crash-left pass cannot echo our notice as a reply ----
conn.execute("DELETE FROM session_admissions")
conn.execute("DELETE FROM state_meta")
conn.commit()
db.aibridge_settled_at_boot = set()
c1 = add("c1", native_payload("lost twice"), generation=6)
mark(c1)
c2 = add("c2", native_payload("lost once"), generation=6)
c3 = add("c3", {"text": "viewer"}, principal="viewer", generation=6)  # stays unknown: upstream's hook clears it
mod.auto_resume_unknown_at_boot(db, 4)
check("only the twice-lost session is recorded", db.aibridge_settled_at_boot == {"c1"}, db.aibridge_settled_at_boot)
Entry = types.SimpleNamespace
entries = [Entry(session_key=k, session_id=k, active_turn_token="tok-" + k) for k in ("c1", "c2", "c3", "c4")]
cleared = []
store = types.SimpleNamespace(list_sessions=lambda: entries, clear_turn_active=lambda key, tok: cleared.append(key))
rt = types.ModuleType("rt")
exec(compile(open(paths["run_runtime.py"]).read(), "rt.py", "exec"), rt.__dict__)
rt.release_unknown_turn_markers(types.SimpleNamespace(session_store=store, authorities=[types.SimpleNamespace(persistence=db)]))
check("the hook releases the twice-settled session's marker and upstream's unknown one, and nothing else",
      sorted(cleared) == ["c1", "c3"], cleared)
db.aibridge_settled_at_boot = set()
cleared.clear()
conn.execute("UPDATE session_admissions SET status='queued' WHERE status='unknown'")
conn.commit()
rt.release_unknown_turn_markers(types.SimpleNamespace(session_store=store, authorities=[types.SimpleNamespace(persistence=db)]))
check("with nothing unknown and nothing settled at boot no marker is touched", cleared == [], cleared)
check("the settled set joins the hook's set before its emptiness test",
      open(paths["run_runtime.py"]).read().index("aibridge_settled_at_boot") < open(paths["run_runtime.py"]).read().index("if not unknown:"))
conn.execute("DELETE FROM session_admissions")
conn.execute("DELETE FROM state_meta")
ledger.execute("DELETE FROM delivery_obligations")
conn.commit()
ledger.commit()


class ExplodingDB:
    def _read_ctx(self):
        raise OSError("db gone")


check("the boot call site swallows any failure (the gateway must start)", mod.auto_resume_unknown_at_boot(ExplodingDB(), 4) is None)
conn.execute("DELETE FROM session_admissions")
b6 = add("b6", {"text": "hi", "api_turn_v1": {}}, principal="api", generation=2)
mod.auto_resume_unknown(db, 4)
check("an API turn is still just settled, no line owed", st(b6) == ("terminal", "interrupted")
      and ledger.execute("SELECT COUNT(*) FROM delivery_obligations").fetchone()[0] == 0)

# ---- 2 + 3) one note, naming the cut-off tool call; the person's text once ----
def turn(sid, rows, text, admitted=True):
    """A session with a transcript (role, content, tool_calls, tool_call_id) and a marked admission carrying *text*."""
    conn.execute("INSERT OR IGNORE INTO sessions(id) VALUES(?)", (sid,))
    for role, content, calls, call_id in rows:
        conn.execute("INSERT INTO messages(session_id,role,content,timestamp,tool_calls,tool_call_id) VALUES(?,?,?,?,?,?)",
                     (sid, role, content, time.time(), json.dumps(calls) if calls is not None else None, call_id))
    aid = add(sid, native_payload(text), generation=1, text_age=1)
    conn.execute("DELETE FROM messages WHERE session_id=? AND role='user' AND content='x'", (sid,))
    if admitted:
        mark(aid)
    conn.commit()
    return aid


def call(cid, name, args):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}


def model_view(user_row, replay):
    """What the model reads once Hermes merges the stored user row with the replay message that follows it."""
    return user_row + "\n\n" + replay


GENERIC = mod.REPLAY_NOTE
a_ = turn("n1", [("user", "turn one", None, None), ("assistant", "ans", None, None), ("user", "SLOW job please", None, None)],
          "SLOW job please")
out = mod.replay_text_for(db, a_, "SLOW job please")
check("killed mid model call: the row is in the history, so the replay is the note alone", out == GENERIC, out)
check("...and the model reads the person's text exactly once", model_view("SLOW job please", out).count("SLOW job please") == 1)
check("...with no stock note in it", "Do NOT re-execute" not in out and "skip any unfinished work" not in out and out.count("[SYSTEM:") == 1)

b_ = turn("n2", [("user", "t", None, None), ("assistant", "a", None, None), ("user", "run the long command", None, None),
                 ("assistant", "", [call("c1", "terminal", {"command": "sleep 30; echo REPLAY-DONE"})], None)], "run the long command")
out = mod.replay_text_for(db, b_, "run the long command")
check("killed during a terminal call: the note names it and its command", out == (
    "[SYSTEM: this turn was interrupted by a restart while running: terminal sleep 30; echo REPLAY-DONE. Check whether it already "
    "took effect before running it again; it may have completed partly.]"), out)
check("...the person's text is not repeated", "run the long command" not in out and out.count("[SYSTEM:") == 1)

c_ = turn("n3", [("user", "do two things", None, None), ("assistant", "first", [call("c1", "read_file", {"path": "/a"})], None),
                 ("tool", "{}", None, "c1"), ("assistant", "", [call("c2", "web_search", {"query": "weather in Rosario"})], None)],
          "do two things")
out = mod.replay_text_for(db, c_, "do two things")
check("a call that already has its result is not named; the unanswered one is, with its JSON arguments",
      'web_search {"query": "weather in Rosario"}' in out and "read_file" not in out, out)
check("a note-wide invariant: one text, one note", out.count("[SYSTEM:") == 1 and "do two things" not in out)

d_ = turn("n4", [("user", "go", None, None), ("assistant", "step", [call("c1", "read_file", {"path": "/a"})], None), ("tool", "{}", None, "c1")], "go")
check("the last tool finished and the restart came during the next model call: generic note, text from the row",
      mod.replay_text_for(db, d_, "go") == GENERIC)

e_ = turn("n5", [("user", "earlier ok", None, None), ("assistant", "done earlier", None, None)], "ok")
out = mod.replay_text_for(db, e_, "ok")
check("no user row of this turn in the transcript (never written): the note and the whole text", out == GENERIC + "\n\nok", out)

f_ = turn("n6", [("user", "ok", None, None), ("assistant", "That was the answer", None, None)], "ok")
out = mod.replay_text_for(db, f_, "ok")
check("an identical earlier message that already got its reply is not mistaken for this one", out == GENERIC + "\n\nok", out)

g_ = turn("n7", [("user", "photo of a receipt", None, None), ("assistant", "", [call("c1", "vision_analyze", {"image": "x"})], None)],
          "photo of a receipt\n[Image attached: /workdir/a.jpg]")
out = mod.replay_text_for(db, g_, "photo of a receipt\n[Image attached: /workdir/a.jpg]")
check("text that differs from the stored row (attachments) is sent whole, after the note", out.endswith("\n\nphoto of a receipt\n[Image attached: /workdir/a.jpg]")
      and "vision_analyze" in out, out)

h_ = turn("n8", [("user", "long", None, None), ("assistant", "", [call("c1", "terminal", {"command": "echo " + "x" * 500 + "\n  y"})], None)], "long")
out = mod.replay_text_for(db, h_, "long")
preview = out.split("while running: terminal ")[1].split(". Check whether")[0]
check("the argument preview is one line of at most 200 characters", len(preview) == 200 and preview.endswith("...") and "\n" not in out, (len(preview), out[:120]))

i_ = turn("n9", [("user", "many", None, None), ("assistant", "", [call("c1", "terminal", "echo 1"), call("c2", "terminal", "echo 2"),
                                                                 call("c3", "terminal", "echo 3"), call("c4", "terminal", "echo 4")], None)], "many")
out = mod.replay_text_for(db, i_, "many")
check("parallel cut-off calls are all named (up to three)", "terminal echo 1; terminal echo 2; terminal echo 3." in out and "echo 4" not in out, out)

j_ = turn("n10", [("user", "bad", None, None)], "bad")
conn.execute("INSERT INTO messages(session_id,role,content,timestamp,tool_calls) VALUES('n10','assistant','',?,?)", (time.time(), '[{"id":"c1","function":{"name":"terminal","argu'))
conn.commit()
check("a half-written tool_calls column falls back to the generic note", mod.replay_text_for(db, j_, "bad") == GENERIC)
check("an admission that was never replayed gets nothing", mod.replay_text_for(db, turn("n11", [("user", "p", None, None)], "p", admitted=False), "p") is None)
check("a non-text event is left alone", mod.replay_text_for(db, a_, None) is None)

_real_tail = mod._interrupted_tail
mod._interrupted_tail = lambda *a: (_ for _ in ()).throw(OSError("boom"))
out = mod.replay_text_for(db, a_, "SLOW job please")
mod._interrupted_tail = _real_tail
check("an unreadable transcript never drops the message: note + whole text", out == GENERIC + "\n\nSLOW job please", out)

# the execute_admission hook and the run_turn_runner hook, run from the patched stand-ins
stub("gateway.session_unattended_unknown", **{k: getattr(mod, k) for k in dir(mod) if not k.startswith("__")})
ing = types.ModuleType("ing")
exec(compile(open(paths["session_ingress.py"]).read(), "ing.py", "exec"), ing.__dict__)


class Ev:
    def __init__(self, text):
        self.text, self.internal = text, False


class A:
    def __init__(self, text):
        self.persistence, self.event = db, Ev(text)


ev = asyncio.run(ing.execute_admission(A("run the long command"), None, {"admission_id": b_})).text
check("execute_admission hands the turn the note naming the tool call", ev == mod.replay_text_for(db, b_, "run the long command") and "terminal sleep 30" in ev)
check("a message that was not replayed runs unchanged", asyncio.run(ing.execute_admission(A("hello"), None, {"admission_id": "never-replayed"})).text == "hello")
check("a media event with a list payload is untouched", asyncio.run(ing.execute_admission(A([1]), None, {"admission_id": b_})).text == [1])

run = types.ModuleType("run")
exec(compile(open(paths["run_turn_runner.py"]).read(), "run.py", "exec"), run.__dict__)
ctx = types.SimpleNamespace(message=ev)
out = run.TurnRunner().prep(ctx, True, True, True, [{"role": "tool"}])
check("a replayed turn gets no stock resume note and no stock tool-tail note", out == ev and "STOCK" not in out)
check("any other message still gets Hermes's own notes",
      run.TurnRunner().prep(types.SimpleNamespace(message="hi"), True, True, False, []).startswith("STOCK-RESUME-NOTE")
      and run.TurnRunner().prep(types.SimpleNamespace(message="hi"), False, True, False, [{"role": "tool"}]).startswith("STOCK-TOOL-TAIL-NOTE"))
check("the replay detector matches only our note", mod.is_replay_text(GENERIC + "\n\nx") and mod.is_replay_text(ev)
      and not mod.is_replay_text("[System note: The previous turn was interrupted by a gateway restart") and not mod.is_replay_text(None))

print()
if fails:
    print("%d FAILED: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("all admission_auto_resume checks passed")
