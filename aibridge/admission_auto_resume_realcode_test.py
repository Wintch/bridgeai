#!/usr/bin/env python3
"""Real-code boot test for patches/admission_auto_resume.py (the stand-in selftest cannot show this one).

Runs the real v0.23.1 boot sequence (real SessionStore/SQLite, two owner epochs, the real delivery ledger and the real
`_ledger_crash_left_replies`) on a tree patched with every aibridge patch in Dockerfile order. A person's turn that
was already replayed once and is lost again must leave exactly ONE owed delivery (our plain line) and no crash-left
"Recovered reply" row; a turn lost for the first time must still be requeued and resumed.
Usage: <hermes venv python> admission_auto_resume_realcode_test.py <patched hermes tree>"""
import asyncio, os, sqlite3, sys, tempfile, types, time
tree = os.path.abspath(sys.argv[1])
sys.path.insert(0, tree)
home = tempfile.mkdtemp(prefix='hermes-realcode-')
os.environ['HERMES_HOME'] = home
os.environ['HOME'] = home
fails = []
def check(name, cond, detail=''):
    print(('ok   ' if cond else 'FAIL ') + name + ('' if cond else '  ' + str(detail)))
    if not cond: fails.append(name)

from types import SimpleNamespace
from gateway.config import GatewayConfig, Platform
from gateway.session import SessionSource, SessionStore, AsyncSessionStore
from gateway.session_authority import LiveSession, initialize_session_authority
from gateway.session_unattended_unknown import REPLAY_META_PREFIX, REPLAY_TWICE_NOTICE, REPLAY_TWICE_TO_PERSON
from gateway.run_runtime import release_unknown_turn_markers
from gateway.run_startup import GatewayStartupMixin
from hermes_state_runtime import admit_session_input, claim_session_input, list_session_admissions
from gateway import delivery_ledger


class Runner(GatewayStartupMixin):
    pass


async def main(second_replay_marker=True):
    store = SessionStore(__import__('pathlib').Path(home) / 'sessions', GatewayConfig())
    db = store._db
    runner = SimpleNamespace(_session_db=db, session_store=store, _draining=False, _handle_message=None,
                             _adapter_for_source=lambda s: None)
    source = SessionSource(platform=Platform.TELEGRAM, chat_id='1001', chat_type='dm', user_id='1001')
    entry = store.get_or_create_session(source)
    sid, key = entry.session_id, entry.session_key
    first = await initialize_session_authority(runner, profile_id='p', instance_id='owner-1')
    # the replay turn: admitted by person, claimed, marked replayed once, running (marker + user row + tool call row)
    row = admit_session_input(db, epoch=first.epoch, principal_id='messaging:[null,"telegram","1001",null,null]',
                              session_id=sid, request_id='m1',
                              payload={'text': 'HEAD', 'native_text_v1': {
                                  'route': key, 'source': {'platform': 'telegram', 'chat_id': '1001'}}})
    aid = row['admission_id']
    claim_session_input(db, epoch=first.epoch, session_id=sid)
    db._execute_write(lambda c: c.execute('INSERT INTO state_meta(key,value) VALUES(?,?)',
                                          (REPLAY_META_PREFIX + aid, str(first.epoch))))
    db.append_message(sid, 'user', 'HEAD')
    token = store.mark_turn_active(key)
    check('the replay turn left an active-turn marker', bool(token))
    # a second chat whose turn was lost for the first time: boot requeues it, nothing is owed, its marker stays
    source_b = SessionSource(platform=Platform.TELEGRAM, chat_id='2002', chat_type='dm', user_id='2002')
    entry_b = store.get_or_create_session(source_b)
    row_b = admit_session_input(db, epoch=first.epoch, principal_id='messaging:[null,"telegram","2002",null,null]',
                                session_id=entry_b.session_id, request_id='m2',
                                payload={'text': 'HEADB', 'native_text_v1': {
                                    'route': entry_b.session_key, 'source': {'platform': 'telegram', 'chat_id': '2002'}}})
    claim_session_input(db, epoch=first.epoch, session_id=entry_b.session_id)
    db.append_message(entry_b.session_id, 'user', 'HEADB')
    token_b = store.mark_turn_active(entry_b.session_key)
    # kill; restart: boot recovery fences unknown and our patch settles the twice-lost turn
    second = await initialize_session_authority(runner, profile_id='p', instance_id='owner-2')
    st = {r['admission_id']: (r['status'], r['outcome']) for r in list_session_admissions(db, session_id=sid, pending_only=False)}
    check('the twice-lost turn is settled interrupted at boot', st.get(aid) == ('terminal', 'interrupted'), st)
    msgs = db.get_messages(sid)
    check('transcript ends with our notice', msgs[-1]['role'] == 'assistant' and msgs[-1]['content'] == REPLAY_TWICE_NOTICE, msgs[-1])
    runner.session_authority = second
    release_unknown_turn_markers(runner)
    # the real unclean-start pass
    r = Runner()
    r.session_store = store
    r.async_session_store = AsyncSessionStore(store)
    r._media_delivery_scope_for_source = lambda origin: __import__('contextlib').nullcontext()
    ledgered = await r._ledger_crash_left_replies(3600)
    resumed = await r.async_session_store.recover_interrupted_turns(max_age_seconds=3600)
    with delivery_ledger._DB_LOCK, delivery_ledger._transaction() as conn:
        owed = conn.execute('SELECT content, state FROM delivery_obligations').fetchall()
    eb = next(e for e in store.list_sessions() if e.session_key == entry_b.session_key)
    stb = {r['admission_id']: r['status'] for r in list_session_admissions(db, session_id=entry_b.session_id, pending_only=False)}
    check('a turn lost once is requeued, not settled', stb.get(row_b['admission_id']) == 'queued', stb)
    check('its marker was left to Hermes own pass (promoted to resume_pending, nothing ledgered for it)',
          eb.resume_pending and not eb.active_turn_token and resumed == 1, (eb.resume_pending, eb.active_turn_token, resumed))
    check('exactly one owed delivery', len(owed) == 1, owed)
    check('it is our plain line', [o[0] for o in owed] == [REPLAY_TWICE_TO_PERSON], owed)
    check('no crash-left reply was ledgered', ledgered == 0, ledgered)
    check('the marker is cleared', not store.get_or_create_session(source).active_turn_token if False else
          not next(e for e in store.list_sessions() if e.session_key == key).active_turn_token)
    e = next(e for e in store.list_sessions() if e.session_key == key)
    check('the twice-settled session is not armed for Hermes empty resume turn', not e.resume_pending, e.resume_pending)
    return owed

owed = asyncio.run(main())
print('owed:', owed)
sys.exit(1 if fails else 0)
